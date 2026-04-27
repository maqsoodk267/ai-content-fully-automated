"""
VoiceEngine — text-to-speech narration.

Strategy (in priority order):
  1. Coqui TTS (local, high quality) — only if installed.
  2. pyttsx3 / espeak system command — offline but lower quality.
  3. Silent placeholder WAV with the spoken duration estimated.
"""

from __future__ import annotations

import gc
import os
import shutil
import subprocess
import threading
import uuid
import wave
from pathlib import Path
from typing import Any, Dict, Optional

from app.engines.base import BaseEngine
from app.engines.media.image_engine import STORAGE_ROOT

VOICE_DIR = STORAGE_ROOT / "voice"
VOICE_DIR.mkdir(parents=True, exist_ok=True)

COQUI_MODEL_OVERRIDE: Dict[str, str] = {
    "en": "tts_models/en/ljspeech/tacotron2-DDC",
    "english": "tts_models/en/ljspeech/tacotron2-DDC",
    "es": "tts_models/es/mai/tacotron2-DDC",
    "spanish": "tts_models/es/mai/tacotron2-DDC",
    "fr": "tts_models/fr/mai/tacotron2-DDC",
    "french": "tts_models/fr/mai/tacotron2-DDC",
    "de": "tts_models/de/thorsten/tacotron2-DDC",
    "german": "tts_models/de/thorsten/tacotron2-DDC",
    "hi": "tts_models/hi/mai/tacotron2-DDC",
    "hindi": "tts_models/hi/mai/tacotron2-DDC",
    "pt": "tts_models/pt/multi-dataset/mai_tts",
    "portuguese": "tts_models/pt/multi-dataset/mai_tts",
    "it": "tts_models/it/mai/tacotron2-DDC",
    "italian": "tts_models/it/mai/tacotron2-DDC",
}
VOICE_STYLE_MAPPING: Dict[str, str] = {
    "motivation": "en-US-JennyNeural",
    "news": "en-UK-SoniaNeural",
    "education": "en-US-GuyNeural",
    "entertainment": "en-US-TonyNeural",
    "business": "en-UK-RyanNeural",
}
MULTILINGUAL_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
COQUI_MODEL_CACHE_DIR = Path(os.environ.get("COQUI_MODEL_CACHE", "~/.cache/coqui_tts_models")).expanduser()
COQUI_MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _coqui_available() -> bool:
    try:
        import TTS  # noqa: F401
        return True
    except Exception:
        return False


def _espeak_path() -> Optional[str]:
    return shutil.which("espeak-ng") or shutil.which("espeak")


class VoiceEngine(BaseEngine):
    name = "voice"
    description = "Text-to-speech narration with multi-backend fallback"

    def __init__(self) -> None:
        super().__init__()
        self._coqui_models: Dict[str, Any] = {}
        self._coqui_unload_timers: Dict[str, threading.Timer] = {}

    # ------------------------------------------------------------------
    def run(
        self,
        text: str,
        *,
        language: str = "en",
        voice: Optional[str] = None,
        category: Optional[str] = None,
        speed: float = 1.0,
    ) -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"path": None, "backend": "none", "duration_s": 0}

        out_path = VOICE_DIR / f"voice_{uuid.uuid4().hex[:10]}.wav"
        voice = voice or self._voice_for_category(category)

        if _coqui_available():
            try:
                return self._coqui_tts(text, str(out_path), language, voice)
            except Exception as exc:
                self.logger.warning("Coqui TTS failed, falling back: %s", exc)

        espeak = _espeak_path()
        if espeak:
            try:
                return self._espeak_tts(text, str(out_path), language, speed, espeak)
            except Exception as exc:
                self.logger.warning("eSpeak failed, falling back: %s", exc)

        return self._silent_placeholder(text, str(out_path))

    # ------------------------------------------------------------------
    def _coqui_tts(self, text: str, out_path: str, language: str,
                    voice: Optional[str]) -> Dict[str, Any]:
        from TTS.api import TTS  # type: ignore

        model_name = self._select_coqui_model(language, voice)
        self.logger.debug("Coqui TTS loading model %s", model_name)
        os.environ.setdefault("COQUI_MODEL_CACHE", str(COQUI_MODEL_CACHE_DIR))

        tts = self._get_coqui_tts(model_name, TTS)
        kwargs: Dict[str, Any] = {}
        speaker = self._select_coqui_speaker(voice)
        if speaker:
            kwargs["speaker"] = speaker
        tts.tts_to_file(text=text, file_path=out_path, **kwargs)
        self._schedule_unload(model_name)

        return {"path": out_path, "backend": "coqui", "duration_s": _wav_duration(out_path),
                "url": f"/media/voice/{Path(out_path).name}"}

    # ------------------------------------------------------------------
    def _get_coqui_tts(self, model_name: str, TTS: Any) -> Any:
        if model_name in self._coqui_models:
            return self._coqui_models[model_name]

        if self._coqui_model_exists(model_name):
            self.logger.debug("Found existing Coqui model cache for %s", model_name)
        else:
            self.logger.debug("Downloading new Coqui model %s into cache %s", model_name, COQUI_MODEL_CACHE_DIR)

        kwargs: Dict[str, Any] = {"model_name": model_name, "progress_bar": False, "gpu": False}
        try:
            kwargs["cache_path"] = str(COQUI_MODEL_CACHE_DIR)
            tts = TTS(**kwargs)
        except TypeError:
            tts = TTS(model_name=model_name, progress_bar=False, gpu=False)

        self._coqui_models[model_name] = tts
        return tts

    def _coqui_model_exists(self, model_name: str) -> bool:
        model_path = COQUI_MODEL_CACHE_DIR / model_name.replace("/", "_")
        return model_path.exists()

    def _voice_for_category(self, category: Optional[str]) -> Optional[str]:
        if not category:
            return None
        return VOICE_STYLE_MAPPING.get(category.strip().lower())

    # ------------------------------------------------------------------
    def _select_coqui_model(self, language: str, voice: Optional[str]) -> str:
        if voice:
            candidate = voice.strip().lower()
            if candidate.startswith("tts_models/"):
                return voice.strip()
            if candidate in COQUI_MODEL_OVERRIDE:
                return COQUI_MODEL_OVERRIDE[candidate]

        return COQUI_MODEL_OVERRIDE.get(language.strip().lower(), MULTILINGUAL_MODEL)

    @staticmethod
    def _select_coqui_speaker(voice: Optional[str]) -> Optional[str]:
        if not voice:
            return None
        clean = voice.strip()
        if clean.startswith("tts_models/"):
            return None
        if clean.lower() in COQUI_MODEL_OVERRIDE:
            return None
        return clean

    def _schedule_unload(self, model_key: str, delay_seconds: int = 60) -> None:
        if model_key in self._coqui_unload_timers:
            existing = self._coqui_unload_timers.pop(model_key)
            existing.cancel()

        timer = threading.Timer(delay_seconds, self._unload_model, args=[model_key])
        timer.daemon = True
        timer.start()
        self._coqui_unload_timers[model_key] = timer

    def _unload_model(self, model_key: str) -> None:
        try:
            if model_key in self._coqui_models:
                del self._coqui_models[model_key]
            if model_key in self._coqui_unload_timers:
                del self._coqui_unload_timers[model_key]
        except Exception:
            pass
        gc.collect()

    def _espeak_tts(self, text: str, out_path: str, language: str,
                    speed: float, espeak: str) -> Dict[str, Any]:
        wpm = max(80, min(280, int(170 * speed)))
        lang_map = {"english": "en", "hindi": "hi", "spanish": "es", "french": "fr",
                    "german": "de", "italian": "it", "portuguese": "pt"}
        lang = lang_map.get(language.lower(), language[:2])
        cmd = [espeak, "-v", lang, "-s", str(wpm), "-w", out_path, text]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        return {"path": out_path, "backend": "espeak", "duration_s": _wav_duration(out_path),
                "url": f"/media/voice/{Path(out_path).name}"}

    def _silent_placeholder(self, text: str, out_path: str) -> Dict[str, Any]:
        # Estimate ~150 wpm and write a silent WAV of that length so the
        # downstream video pipeline still has a valid audio track.
        words = max(1, len(text.split()))
        duration = max(1.0, words / 2.5)  # ~150 wpm
        framerate = 22050
        n_frames = int(duration * framerate)
        with wave.open(out_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(framerate)
            w.writeframes(b"\x00\x00" * n_frames)
        return {"path": out_path, "backend": "silent",
                "duration_s": round(duration, 2),
                "url": f"/media/voice/{Path(out_path).name}",
                "warning": "No TTS backend installed; produced silent placeholder."}


def _wav_duration(path: str) -> float:
    try:
        with wave.open(path, "rb") as w:
            return round(w.getnframes() / float(w.getframerate()), 2)
    except Exception:
        return 0.0
