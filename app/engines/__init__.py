"""
AI engines package.

Importing this package eagerly instantiates every engine so they
self-register in the BaseEngine registry. After import, any caller can do:

    from app.engines import get_engine, list_engines
    quality = get_engine("quality")
    result  = quality(script="...", hooks=[...])
"""

from __future__ import annotations

import logging
from typing import Dict, List

from app.engines.base import BaseEngine, all_engines, get_engine, list_engines, register_engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Eager-instantiate all engines so they register in the BaseEngine registry.
# ---------------------------------------------------------------------------
def _bootstrap() -> None:
    # LLM engines
    from app.engines.llm.content_engine import ContentEngine
    from app.engines.llm.hook_engine import HookEngine
    from app.engines.llm.caption_engine import CaptionEngine
    from app.engines.llm.translation_engine import TranslationEngine
    from app.engines.llm.marketing_engine import MarketingEngine

    # Trends
    from app.engines.trends.trend_engine import TrendEngine
    from app.engines.trends.viral_radar_engine import ViralRadarEngine

    # Media
    from app.engines.media.image_engine import ImageEngine, ThumbnailEngine
    from app.engines.media.voice_engine import VoiceEngine
    from app.engines.media.subtitle_engine import SubtitleEngine
    from app.engines.media.video_engine import VideoEngine
    from app.engines.media.asset_fetch_engine import AssetFetchEngine

    # Quality
    from app.engines.quality.quality_engine import QualityEngine
    from app.engines.quality.engagement_prediction import EngagementPredictionEngine
    from app.engines.quality.optimizer_engines import (
        EmotionalResonanceEngine,
        AttentionOptimizerEngine,
        VisualEnhancementEngine,
    )

    # Learning
    from app.engines.learning.ab_testing import ABTestingEngine
    from app.engines.learning.anti_duplication import AntiDuplicationEngine
    from app.engines.learning.hashtag_learning import HashtagLearningEngine
    from app.engines.learning.timing_engines import (
        BestTimeEngine,
        SkipAnalysisEngine,
        ContentFreshnessEngine,
        ContentDecayEngine,
    )

    # System
    from app.engines.system.approval_engine import ApprovalEngine
    from app.engines.system.moderation_engine import ModerationEngine
    from app.engines.system.cost_engine import CostEngine
    from app.engines.system.resource_manager import ResourceManager

    # Strategy
    from app.engines.strategy.strategy_engines import (
        ContentBucketsEngine,
        SeriesBuilderEngine,
        PlatformPsychologyEngine,
        CommentCTAEngine,
        HumanizedContentEngine,
        CategoryRouterEngine,
        CompetitorEngine,
    )

    # Distribution
    from app.engines.distribution.account_manager import AccountManager
    from app.engines.distribution.human_mimicry import HumanMimicryEngine
    from app.engines.distribution.shadowban_detection import ShadowbanDetectionEngine
    from app.engines.distribution.scheduler import SchedulerEngine
    from app.engines.distribution.publisher_engine import PublisherEngine

    classes = [
        ContentEngine, HookEngine, CaptionEngine, TranslationEngine, MarketingEngine,
        TrendEngine, ViralRadarEngine,
        ImageEngine, ThumbnailEngine, VoiceEngine, SubtitleEngine, VideoEngine, AssetFetchEngine,
        QualityEngine, EngagementPredictionEngine,
        EmotionalResonanceEngine, AttentionOptimizerEngine, VisualEnhancementEngine,
        ABTestingEngine, AntiDuplicationEngine, HashtagLearningEngine,
        BestTimeEngine, SkipAnalysisEngine, ContentFreshnessEngine, ContentDecayEngine,
        ApprovalEngine, ModerationEngine, CostEngine, ResourceManager,
        ContentBucketsEngine, SeriesBuilderEngine, PlatformPsychologyEngine,
        CommentCTAEngine, HumanizedContentEngine, CategoryRouterEngine, CompetitorEngine,
        AccountManager, HumanMimicryEngine, ShadowbanDetectionEngine,
        SchedulerEngine, PublisherEngine,
    ]
    for cls in classes:
        try:
            cls()  # constructor self-registers
        except Exception as exc:  # noqa: BLE001
            logger.warning("Engine %s failed to initialize: %s", cls.__name__, exc)


_bootstrap()


def health_summary() -> Dict[str, dict]:
    """Quick snapshot of every registered engine."""
    return {name: eng.health() for name, eng in all_engines().items()}


def stats_summary() -> List[dict]:
    return [eng.stats() for eng in all_engines().values()]


__all__ = [
    "BaseEngine", "register_engine", "get_engine", "list_engines",
    "all_engines", "health_summary", "stats_summary",
]
