"""
Learning loop endpoints — A/B testing, anti-duplication, hashtag learning,
best-time, freshness, decay, skip analysis.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.engines import get_engine

router = APIRouter(prefix="/learning", tags=["learning"])


# ---------------------------------------------------------------------------
# A/B testing — Beta-Bandit
# ---------------------------------------------------------------------------
class ABCreateRequest(BaseModel):
    name: str
    variants: List[str]


@router.post("/ab/create")
async def ab_create(payload: ABCreateRequest) -> Dict[str, Any]:
    return get_engine("ab_testing")(action="create", **payload.dict())


@router.get("/ab/{test_id}/pick")
async def ab_pick(test_id: str) -> Dict[str, Any]:
    return get_engine("ab_testing")(action="pick", test_id=test_id)


class ABReportRequest(BaseModel):
    variant_id: str
    converted: bool = False


@router.post("/ab/{test_id}/report")
async def ab_report(test_id: str, payload: ABReportRequest) -> Dict[str, Any]:
    return get_engine("ab_testing")(action="report", test_id=test_id,
                                     variant_id=payload.variant_id,
                                     converted=payload.converted)


@router.post("/ab/{test_id}/winner")
async def ab_winner(test_id: str) -> Dict[str, Any]:
    return get_engine("ab_testing")(action="winner", test_id=test_id)


@router.get("/ab")
async def ab_list() -> Dict[str, Any]:
    return {"tests": get_engine("ab_testing")(action="list")}


# ---------------------------------------------------------------------------
# Anti-duplication
# ---------------------------------------------------------------------------
class DupCheckRequest(BaseModel):
    kind: str = Field("text", description="text|image|video")
    text: Optional[str] = None
    path: Optional[str] = None
    threshold: Optional[float] = None


@router.post("/duplicates/check")
async def dup_check(payload: DupCheckRequest) -> Dict[str, Any]:
    args: Dict[str, Any] = {"kind": payload.kind}
    if payload.kind == "text" and payload.text is not None:
        args["text"] = payload.text
    elif payload.kind in ("image", "video") and payload.path:
        args["path"] = payload.path
    if payload.threshold is not None:
        args["threshold"] = payload.threshold
    return get_engine("anti_duplication")(**args)


class DupCheckBeforeGenRequest(BaseModel):
    script: str
    category: str
    platform: str
    account_id: Optional[str] = None
    check_window_days: int = 30


@router.post("/duplicates/check-before-generate")
async def dup_check_before_generate(payload: DupCheckBeforeGenRequest) -> Dict[str, Any]:
    return get_engine("anti_duplication").check_before_generation(
        script=payload.script,
        category=payload.category,
        platform=payload.platform,
        account_id=payload.account_id,
        check_window_days=payload.check_window_days,
    )


# ---------------------------------------------------------------------------
# Hashtag learning
# ---------------------------------------------------------------------------
class HashtagIngestRequest(BaseModel):
    records: List[Dict[str, Any]]


@router.post("/hashtags/ingest")
async def hashtag_ingest(payload: HashtagIngestRequest) -> Dict[str, Any]:
    return get_engine("hashtag_learning")(action="ingest", records=payload.records)


@router.get("/hashtags/recommend")
async def hashtag_recommend(topic: Optional[str] = None,
                             count: int = 12) -> Dict[str, Any]:
    return get_engine("hashtag_learning")(action="recommend", topic=topic, count=count)


@router.get("/hashtags/stats")
async def hashtag_stats() -> Dict[str, Any]:
    return get_engine("hashtag_learning")(action="stats")


# ---------------------------------------------------------------------------
# Best-time
# ---------------------------------------------------------------------------
@router.get("/best-time")
async def best_time(platform: str, top_k: int = 4) -> Dict[str, Any]:
    return get_engine("best_time")(action="best_times", platform=platform, top_k=top_k)


class BestTimeIngest(BaseModel):
    records: List[Dict[str, Any]]


@router.post("/best-time/ingest")
async def best_time_ingest(payload: BestTimeIngest) -> Dict[str, Any]:
    return get_engine("best_time")(action="ingest", records=payload.records)


# ---------------------------------------------------------------------------
# Skip analysis
# ---------------------------------------------------------------------------
class SkipRequest(BaseModel):
    retention_curve: List[float]
    duration_s: float = 30.0


@router.post("/skip-analysis")
async def skip_analysis(payload: SkipRequest) -> Dict[str, Any]:
    return get_engine("skip_analysis")(**payload.dict())


# ---------------------------------------------------------------------------
# Freshness & decay
# ---------------------------------------------------------------------------
@router.get("/freshness")
async def freshness(topic: str, cooldown_days: int = 7) -> Dict[str, Any]:
    return get_engine("content_freshness")(topic=topic, cooldown_days=cooldown_days)


@router.get("/decay")
async def decay(hours_since_publish: float,
                 initial_engagement: float = 1.0,
                 half_life_hours: float = 18.0) -> Dict[str, Any]:
    return get_engine("content_decay")(hours_since_publish=hours_since_publish,
                                        initial_engagement=initial_engagement,
                                        half_life_hours=half_life_hours)


# ---------------------------------------------------------------------------
# Skip Analysis
# ---------------------------------------------------------------------------
class SkipEventRequest(BaseModel):
    post_id: str
    skip_time_seconds: float
    platform: str
    category: str = "general"


@router.post("/skip-analysis/track")
async def track_skip(payload: SkipEventRequest) -> Dict[str, Any]:
    engine = get_engine("skip_analysis")
    engine.track_skip(
        post_id=payload.post_id,
        skip_time_seconds=payload.skip_time_seconds,
        platform=payload.platform,
        category=payload.category,
    )
    return {"status": "recorded"}


@router.get("/skip-analysis/patterns")
async def skip_patterns(category: Optional[str] = None) -> Dict[str, Any]:
    return get_engine("skip_analysis").analyze_patterns(category)


@router.post("/skip-analysis/update-templates")
async def update_skip_templates() -> Dict[str, Any]:
    return get_engine("skip_analysis").update_templates()


# ---------------------------------------------------------------------------
# Best Time Learning
# ---------------------------------------------------------------------------
class BestTimeTrackRequest(BaseModel):
    post_id: str
    published_at: str
    engagement_rate: float
    platform: str
    account_id: str


@router.post("/best-time/track")
async def track_best_time(payload: BestTimeTrackRequest) -> Dict[str, Any]:
    engine = get_engine("best_time")
    engine.track_engagement(
        post_id=payload.post_id,
        published_at=payload.published_at,
        engagement_rate=payload.engagement_rate,
        platform=payload.platform,
        account_id=payload.account_id,
    )
    return {"status": "recorded"}


@router.get("/best-time/predict")
async def predict_best_time(platform: str, account_id: str, timezone: str = "UTC") -> Dict[str, Any]:
    return get_engine("best_time").predict_best_time(platform, account_id, timezone)


@router.get("/best-time/auto-update")
async def auto_update_scheduler() -> Dict[str, Any]:
    return get_engine("best_time").auto_update_scheduler()


# ---------------------------------------------------------------------------
# Hashtag Learning
# ---------------------------------------------------------------------------
class HashtagTrackRequest(BaseModel):
    hashtags: List[str]
    impressions: float
    engagement: float
    platform: str = "general"
    category: str = "general"


@router.post("/hashtags/track")
async def track_hashtag_performance(payload: HashtagTrackRequest) -> Dict[str, Any]:
    engine = get_engine("hashtag_learning")
    engine.track_performance(
        hashtags=payload.hashtags,
        impressions=payload.impressions,
        engagement=payload.engagement,
        platform=payload.platform,
        category=payload.category,
    )
    return {"status": "recorded"}


@router.get("/hashtags/recommend")
async def recommend_hashtags_v2(category: str, platform: str, count: int = 10) -> Dict[str, Any]:
    return {"recommended": get_engine("hashtag_learning").recommend_hashtags(category, platform, count)}


@router.post("/hashtags/cleanup")
async def cleanup_hashtags(threshold_engagement: float = 0.5) -> Dict[str, Any]:
    return get_engine("hashtag_learning").drop_poor_hashtags(threshold_engagement)


# ---------------------------------------------------------------------------
# System Engines
# ---------------------------------------------------------------------------
class ApprovalEvaluateRequest(BaseModel):
    content: Dict[str, Any]


class ApprovalAutoPilotRequest(BaseModel):
    enabled: bool
    account_id: Optional[str] = None


@router.post("/approval/evaluate")
async def evaluate_approval(payload: ApprovalEvaluateRequest) -> Dict[str, Any]:
    return get_engine("approval").evaluate_content(payload.content)


@router.post("/approval/auto-pilot")
async def approval_auto_pilot(payload: ApprovalAutoPilotRequest) -> Dict[str, Any]:
    return get_engine("approval").auto_pilot_mode(
        enabled=payload.enabled,
        account_id=payload.account_id,
    )


class ModerationCheckRequest(BaseModel):
    content_id: str
    text: str
    image_path: Optional[str] = None


@router.post("/moderation/check")
async def moderation_check(payload: ModerationCheckRequest) -> Dict[str, Any]:
    engine = get_engine("moderation")
    return engine.moderate_content(
        content_id=payload.content_id,
        text=payload.text,
        image_path=payload.image_path,
    )


@router.get("/moderation/quarantine")
async def moderation_quarantine_queue(limit: int = 50) -> Dict[str, Any]:
    return get_engine("moderation").get_quarantine_queue(limit)


class ModerationReviewRequest(BaseModel):
    content_id: str
    decision: str
    reviewer: str
    notes: Optional[str] = ""


@router.post("/moderation/review")
async def moderation_review(payload: ModerationReviewRequest) -> Dict[str, Any]:
    return get_engine("moderation").review_quarantined_content(
        content_id=payload.content_id,
        decision=payload.decision,
        reviewer=payload.reviewer,
        notes=payload.notes,
    )


class CostTrackRequest(BaseModel):
    service: str
    cost: float
    user_id: str
    metadata: Optional[Dict[str, Any]] = None


@router.post("/cost/track")
async def track_cost(payload: CostTrackRequest) -> Dict[str, Any]:
    return get_engine("cost").track_api_call(
        service=payload.service,
        cost=payload.cost,
        user_id=payload.user_id,
        metadata=payload.metadata,
    )


class CostBudgetRequest(BaseModel):
    user_id: str
    budget_limit: float
    period: str = "monthly"


@router.post("/cost/check-budget")
async def check_cost_budget(payload: CostBudgetRequest) -> Dict[str, Any]:
    return get_engine("cost").check_budget(
        user_id=payload.user_id,
        budget_limit=payload.budget_limit,
        period=payload.period,
    )


@router.get("/cost/report")
async def cost_report(user_id: Optional[str] = None, period: str = "monthly") -> Dict[str, Any]:
    return get_engine("cost").get_usage_report(user_id=user_id, period=period)


class CostSetBudgetRequest(BaseModel):
    user_id: str
    budget_limit: float


@router.post("/cost/set-budget")
async def set_cost_budget(payload: CostSetBudgetRequest) -> Dict[str, Any]:
    return get_engine("cost").set_budget(payload.user_id, payload.budget_limit)


class ResourceAcquireRequest(BaseModel):
    job_type: str
    job_id: str
    metadata: Optional[Dict[str, Any]] = None


@router.post("/resources/acquire")
async def acquire_resource_slot(payload: ResourceAcquireRequest) -> Dict[str, Any]:
    return get_engine("resource_manager").acquire_slot(
        job_type=payload.job_type,
        job_id=payload.job_id,
        metadata=payload.metadata,
    )


class ResourceReleaseRequest(BaseModel):
    job_id: str


@router.post("/resources/release")
async def release_resource_slot(payload: ResourceReleaseRequest) -> Dict[str, Any]:
    return get_engine("resource_manager").release_slot(job_id=payload.job_id)


@router.get("/resources/status")
async def resource_status() -> Dict[str, Any]:
    return get_engine("resource_manager").get_status()


@router.get("/resources/can-run-heavy")
async def resource_can_run_heavy() -> Dict[str, Any]:
    return get_engine("resource_manager").can_run_heavy_job()


class ResourceLimitUpdateRequest(BaseModel):
    cpu_limit: Optional[float] = None
    memory_limit: Optional[float] = None
    gpu_limit: Optional[float] = None


@router.post("/resources/set-limits")
async def set_resource_limits(payload: ResourceLimitUpdateRequest) -> Dict[str, Any]:
    return get_engine("resource_manager").set_resource_limits(
        cpu_limit=payload.cpu_limit,
        memory_limit=payload.memory_limit,
        gpu_limit=payload.gpu_limit,
    )


class ResourceScaleRequest(BaseModel):
    category: str
    new_limit: int


@router.post("/resources/scale")
async def resource_scale(payload: ResourceScaleRequest) -> Dict[str, Any]:
    return get_engine("resource_manager").scale_job_slots(
        category=payload.category,
        new_limit=payload.new_limit,
    )
