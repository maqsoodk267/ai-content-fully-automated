"""
Engine functionality tests
"""

import inspect
import os
import tempfile
from typing import Optional

import pytest

from app.engines.llm.translation_engine import TranslationEngine
from app.engines.media.image_engine import ImageEngine
from app.engines.media.subtitle_engine import SubtitleEngine
from app.engines.learning.anti_duplication import AntiDuplicationEngine
from app.engines.media.video_engine import VideoEngine, ffmpeg_available
from app.engines.media.voice_engine import VoiceEngine


def test_content_engine():
    """Test content generation engine"""
    pass


def test_trend_engine():
    """Test trend detection engine"""
    pass


def test_video_engine():
    """Test video generation engine"""
    if not ffmpeg_available():
        pytest.skip("ffmpeg is not installed in this environment")

    image = ImageEngine().run("Video engine test", subtitle="Transitions and motion")
    voice = VoiceEngine().run("This is a short demo narration for the new video engine.")
    subtitles = SubtitleEngine().run(
        script="This is a short demo narration for the new video engine.",
        duration_s=voice["duration_s"],
    )

    result = VideoEngine().run(
        image_paths=[image["path"]],
        audio_path=voice["path"],
        subtitle_path=subtitles["path"],
        duration_per_image=3.0,
        transition_duration=0.5,
        zoom_cuts=True,
        speed_ramp=True,
        width=540,
        height=960,
        fps=15,
    )

    assert result["path"] is not None
    assert os.path.exists(result["path"])
    assert result["duration_s"] > 0
    assert result["segments"] == 1
    os.remove(result["path"])


def test_video_engine_text_animations():
    if not ffmpeg_available():
        pytest.skip("ffmpeg is not installed in this environment")

    image = ImageEngine().run("Text animation demo", subtitle="Animated text overlay")
    voice = VoiceEngine().run("This content includes animated textual overlays.")

    result = VideoEngine().run(
        image_paths=[image["path"]],
        audio_path=voice["path"],
        duration_per_image=3.0,
        transition_duration=0.5,
        width=540,
        height=960,
        fps=15,
        text_animations=[
            {"type": "fade", "text": "Hello world", "position": "top", "duration": 2.5}
        ],
    )

    assert result["path"] is not None
    assert os.path.exists(result["path"])
    assert result["duration_s"] > 0
    os.remove(result["path"])


def test_video_engine_glitch_effect_signature():
    import inspect

    sig = inspect.signature(VideoEngine.run)
    assert "glitch_effect" in sig.parameters
    assert "glitch_intensity" in sig.parameters


def test_video_engine_glitch_filter_generation():
    effects = VideoEngine._normalize_glitch_effects(["rgb_split", "frame_shift"])
    assert effects == ["rgb_split", "frame_shift"]

    filter_desc = VideoEngine._build_glitch_filters("[in]", effects, 0.7, 540, 960)
    assert "[glitched]" in filter_desc
    assert "split=3" in filter_desc
    assert "translate" in filter_desc


def test_translation_engine_cache_and_fallback(monkeypatch):
    class DummyRedis:
        def __init__(self):
            self.store = {}

        def get(self, key):
            return self.store.get(key)

        def setex(self, key, ttl, value):
            self.store[key] = value

    engine = TranslationEngine()
    engine._redis = DummyRedis()

    def fake_libre(text, source, target):
        return None

    def fake_helsinki(text, source, target):
        return "Hello English fallback" if target == "en" else None

    monkeypatch.setattr(engine, "_translate_libre", fake_libre)
    monkeypatch.setattr(engine, "_translate_helsinki", fake_helsinki)

    first = engine.run("Bonjour", target_language="spanish", source_language="french")
    assert first["translated"] == "Hello English fallback"
    assert first["target"] == "en"
    assert not first["cached"]

    second = engine.run("Bonjour", target_language="spanish", source_language="french")
    assert second["translated"] == "Hello English fallback"
    assert second["cached"]


def test_anti_duplication_text_hash_fallback():
    engine = AntiDuplicationEngine()
    engine._vector_db = None
    engine._embedding_model = None

    first = engine.check_text("This is a duplicate test.")
    assert first["is_duplicate"] is False
    assert first["method"] == "hash_fallback"

    second = engine.check_text("This is a duplicate test.")
    assert second["is_duplicate"] is True
    assert second["method"] == "hash_fallback"


def test_anti_duplication_image_hash():
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow is required for image hash tests")

    engine = AntiDuplicationEngine()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        path = tmp.name
    try:
        image = Image.new("RGB", (16, 16), color=(255, 0, 0))
        image.save(path)

        first = engine.check_image(path)
        assert first["is_duplicate"] is False
        assert first["method"] == "image_hash"

        second = engine.check_image(path)
        assert second["is_duplicate"] is True
        assert second["method"] == "image_hash"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_anti_duplication_video_fingerprint():
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow is required for video hash tests")

    engine = AntiDuplicationEngine()
    # Create a dummy video-like file, but since no ffmpeg, just test the method
    # For now, test that the method exists and handles missing ffmpeg
    result = engine.check_video("/nonexistent.mp4")
    assert result["is_duplicate"] is False
    assert "reason" in result


def test_voice_engine_multi_language():
    """Test voice generation engine with multi-language fallback"""
    engine = VoiceEngine()
    output = engine.run("Bonjour, ceci est un test.", language="fr", voice=None)
    assert output["path"] is not None
    assert output["duration_s"] > 0
    assert os.path.exists(output["path"])
    os.remove(output["path"])


def test_voice_engine_category_voice_mapping():
    engine = VoiceEngine()
    assert engine._voice_for_category("motivation") == "en-US-JennyNeural"
    assert engine._voice_for_category("News") == "en-UK-SoniaNeural"
    assert engine._voice_for_category("unknown") is None


def test_voice_engine_run_signature():
    sig = inspect.signature(VoiceEngine.run)
    assert "category" in sig.parameters
    assert str(sig.parameters["category"].annotation) == "Optional[str]"


def test_quality_scoring():
    """Test quality scoring engine"""
    pass
