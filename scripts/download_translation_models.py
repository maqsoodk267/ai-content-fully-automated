#!/usr/bin/env python3
"""
Download Translation Models Script

Pre-download Helsinki-NLP translation models for offline use.
Usage: python scripts/download_translation_models.py [model1] [model2] ...

If no models specified, downloads common ones.
"""

import argparse
import os
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.engines.llm.translation_engine import HUGGINGFACE_MODEL_TEMPLATE, LANGUAGE_CODES


def download_model(model_name: str, cache_path: str = None):
    """Download a single model."""
    try:
        from huggingface_hub import snapshot_download
        import psutil
    except ImportError as e:
        print(f"Error: {e}. Install with: pip install huggingface_hub psutil")
        return False

    if cache_path is None:
        cache_path = os.environ.get("TRANSLATION_MODEL_CACHE_PATH") or os.path.expanduser("~/.cache/huggingface")

    # Check disk space
    disk = psutil.disk_usage('/')
    free_gb = disk.free / (1024 ** 3)
    if free_gb < 5:
        print(f"Warning: Low disk space: {free_gb:.1f}GB free. Models require ~300MB each.")

    print(f"Downloading {model_name} to {cache_path}...")
    try:
        snapshot_download(
            repo_id=model_name,
            cache_dir=cache_path,
            local_files_only=False,
            resume_download=True,
        )
        print(f"Successfully downloaded {model_name}")
        return True
    except Exception as e:
        print(f"Failed to download {model_name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Download Helsinki-NLP translation models")
    parser.add_argument("models", nargs="*", help="Model names to download")
    parser.add_argument("--cache-path", help="Cache directory path")
    args = parser.parse_args()

    if args.cache_path:
        os.environ["TRANSLATION_MODEL_CACHE_PATH"] = args.cache_path

    models_to_download = args.models or [
        HUGGINGFACE_MODEL_TEMPLATE.format(src="en", tgt="es"),
        HUGGINGFACE_MODEL_TEMPLATE.format(src="en", tgt="fr"),
        HUGGINGFACE_MODEL_TEMPLATE.format(src="en", tgt="de"),
        HUGGINGFACE_MODEL_TEMPLATE.format(src="es", tgt="en"),
        HUGGINGFACE_MODEL_TEMPLATE.format(src="fr", tgt="en"),
        HUGGINGFACE_MODEL_TEMPLATE.format(src="de", tgt="en"),
    ]

    success_count = 0
    for model in models_to_download:
        if download_model(model, args.cache_path):
            success_count += 1

    print(f"Downloaded {success_count}/{len(models_to_download)} models")


if __name__ == "__main__":
    main()