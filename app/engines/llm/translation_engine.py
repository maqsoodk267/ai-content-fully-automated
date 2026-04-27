"""
TranslationEngine — translate any text into a target language.

Strategy: prefer LibreTranslate for fast local translation, then Helsinki-NLP
models via Hugging Face or local transformers. Cache every response in Redis
and keep a safe English fallback when translation services fail.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.redis_client import get_redis
from app.engines.base import BaseEngine

LANGUAGE_CODES: Dict[str, str] = {
    "english": "en",
    "en": "en",
    "hindi": "hi",
    "hi": "hi",
    "spanish": "es",
    "es": "es",
    "french": "fr",
    "fr": "fr",
    "german": "de",
    "de": "de",
    "portuguese": "pt",
    "pt": "pt",
    "arabic": "ar",
    "ar": "ar",
    "indonesian": "id",
    "id": "id",
    "bengali": "bn",
    "bn": "bn",
    "tamil": "ta",
    "ta": "ta",
    "telugu": "te",
    "te": "te",
    "marathi": "mr",
    "mr": "mr",
    "gujarati": "gu",
    "gu": "gu",
    "punjabi": "pa",
    "pa": "pa",
    "urdu": "ur",
    "ur": "ur",
    "japanese": "ja",
    "ja": "ja",
    "korean": "ko",
    "ko": "ko",
    "chinese": "zh",
    "zh": "zh",
    "russian": "ru",
    "ru": "ru",
    "italian": "it",
    "it": "it",
    "turkish": "tr",
    "tr": "tr",
    "dutch": "nl",
    "nl": "nl",
    "vietnamese": "vi",
    "vi": "vi",
    "thai": "th",
    "th": "th",
    "swahili": "sw",
    "sw": "sw",
    "persian": "fa",
    "fa": "fa",
}

HUGGINGFACE_MODEL_TEMPLATE = "Helsinki-NLP/opus-mt-{src}-{tgt}"
DEFAULT_TARGET = "en"


class TranslationEngine(BaseEngine):
    name = "translation"
    description = "Translate text into another language using open-source translation services"

    def __init__(self) -> None:
        super().__init__()
        self._redis = get_redis()
        self._local_pipelines: Dict[str, Any] = {}
        # Set cache path for transformers if specified
        cache_path = os.environ.get("TRANSLATION_MODEL_CACHE_PATH")
        if cache_path:
            os.environ.setdefault("HF_HOME", cache_path)
            os.environ.setdefault("TRANSFORMERS_CACHE", cache_path)

    def run(
        self,
        text: str,
        *,
        target_language: str,
        source_language: Optional[str] = None,
        preserve_formatting: bool = True,
    ) -> Dict[str, Any]:
        target = self._normalize_lang(target_language) or DEFAULT_TARGET
        source = self._normalize_lang(source_language) if source_language else "auto"

        if source == target:
            return {"translated": text or "", "target": target, "cached": False}

        if not text or not text.strip():
            return {"translated": "", "target": target, "cached": False}

        cache_key = self._cache_key(text, source, target)
        cached = self._redis.get(cache_key)
        if cached:
            return {"translated": cached, "target": target, "cached": True}

        translated = self._translate(text, source, target, preserve_formatting)
        if translated is None and target != DEFAULT_TARGET:
            translated = self._translate(text, source, DEFAULT_TARGET, preserve_formatting)
            target = DEFAULT_TARGET

        if translated is None:
            translated = text

        self._redis.setex(cache_key, settings.translation_cache_ttl_s, translated)
        return {"translated": translated, "target": target, "cached": False}

    def batch(
        self,
        texts: List[str],
        *,
        target_language: str,
        source_language: Optional[str] = None,
    ) -> List[str]:
        return [
            self.run(t, target_language=target_language, source_language=source_language)["translated"]
            for t in texts
        ]

    # ------------------------------------------------------------------
    def _translate(
        self,
        text: str,
        source: str,
        target: str,
        preserve_formatting: bool,
    ) -> Optional[str]:
        if source == target:
            return text

        if settings.libretranslate_url:
            translated = self._translate_libre(text, source, target)
            if translated:
                return translated

        return self._translate_helsinki(text, source, target)

    def _translate_libre(self, text: str, source: str, target: str) -> Optional[str]:
        url = settings.libretranslate_url.strip().rstrip("/")
        if not url:
            return None

        payload = {
            "q": text,
            "source": source if source != "auto" else "auto",
            "target": target,
            "format": "text",
        }
        try:
            response = httpx.post(
                f"{url}/translate",
                json=payload,
                timeout=httpx.Timeout(settings.translation_timeout_libre_s),
            )
            response.raise_for_status()
            data = response.json()
            return data.get("translatedText") or data.get("translation")
        except Exception as exc:
            self.logger.warning("LibreTranslate failed: %s", exc)
            return None

    def _translate_helsinki(self, text: str, source: str, target: str) -> Optional[str]:
        model_name = self._model_name(source, target)
        if not model_name:
            return None

        translated = self._translate_with_transformers(text, model_name)
        if translated:
            return translated

        return self._translate_with_huggingface_api(text, model_name)

    def _translate_with_transformers(self, text: str, model_name: str) -> Optional[str]:
        try:
            from transformers import pipeline

            if not self._ensure_model_downloaded(model_name):
                return None

            if model_name not in self._local_pipelines:
                self._local_pipelines[model_name] = pipeline(
                    "translation",
                    model=model_name,
                    device=-1,
                )
            pipeline_fn = self._local_pipelines[model_name]
            result = pipeline_fn(text, max_length=max(256, len(text) * 2))
            if isinstance(result, list) and result:
                return result[0].get("translation_text")
        except Exception as exc:
            self.logger.debug("Local transformers pipeline failed: %s", exc)
        return None

    def _ensure_model_downloaded(self, model_name: str) -> bool:
        """Check if model exists locally, download if not."""
        try:
            from huggingface_hub import snapshot_download
            import psutil
        except ImportError:
            self.logger.warning("huggingface_hub or psutil not installed, skipping download check")
            return True

        # Check disk space
        disk = psutil.disk_usage('/')
        free_gb = disk.free / (1024 ** 3)
        if free_gb < 5:
            self.logger.warning(f"Low disk space: {free_gb:.1f}GB free. Helsinki models require ~300MB each.")

        # Check if model is already downloaded
        cache_path = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
        model_path = os.path.join(cache_path, "hub", f"models--{model_name.replace('/', '--')}")
        if os.path.exists(model_path):
            self.logger.debug(f"Model {model_name} already exists locally")
            return True

        # Download with progress
        self.logger.info(f"Downloading Helsinki model {model_name} (~300MB)...")
        try:
            snapshot_download(
                repo_id=model_name,
                cache_dir=cache_path,
                local_files_only=False,
                resume_download=True,
            )
            self.logger.info(f"Successfully downloaded {model_name}")
            return True
        except Exception as exc:
            self.logger.error(f"Failed to download model {model_name}: {exc}")
            return False

    def _translate_with_huggingface_api(self, text: str, model_name: str) -> Optional[str]:
        url = f"{settings.huggingface_api_url.rstrip('/')}/models/{model_name}"
        headers = {"Accept": "application/json"}
        if settings.huggingface_api_token:
            headers["Authorization"] = f"Bearer {settings.huggingface_api_token}"

        try:
            response = httpx.post(
                url,
                headers=headers,
                json={"inputs": text},
                timeout=httpx.Timeout(settings.translation_timeout_hf_s),
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return data[0].get("translation_text") or data[0].get("generated_text")
            if isinstance(data, dict) and "translation_text" in data:
                return data["translation_text"]
        except Exception as exc:
            self.logger.warning("Hugging Face translation failed: %s", exc)
        return None

    def _normalize_lang(self, language: Optional[str]) -> Optional[str]:
        if not language:
            return None
        normalized = language.strip().lower()
        return LANGUAGE_CODES.get(normalized, normalized)

    def _model_name(self, source: str, target: str) -> Optional[str]:
        if source == "auto":
            return HUGGINGFACE_MODEL_TEMPLATE.format(src="en", tgt=target)
        if source not in LANGUAGE_CODES.values() or target not in LANGUAGE_CODES.values():
            return None
        return HUGGINGFACE_MODEL_TEMPLATE.format(src=source, tgt=target)

    @staticmethod
    def _cache_key(text: str, source: str, target: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"translation:{source}:{target}:{digest}"
