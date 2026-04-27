"""
Timing-related learning engines:

  - BestTimeEngine: learns best publish times per platform from past performance.
  - SkipAnalysisEngine: detects the moment viewers skip a video.
  - ContentFreshnessEngine: tracks how stale a topic is and recommends rotation.
  - ContentDecayEngine: models how performance decays over time.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.engines.base import BaseEngine


class BestTimeEngine(BaseEngine):
    name = "best_time"
    description = "Learn best publish time-windows per platform and account"

    DEFAULT_TIMES = {
        "instagram": ["09:00", "12:00", "18:00", "21:00"],
        "tiktok":    ["07:00", "12:00", "19:00", "22:00"],
        "youtube":   ["14:00", "16:00", "20:00"],
        "youtube_shorts": ["12:00", "17:00", "21:00"],
        "facebook":  ["09:00", "13:00", "20:00"],
        "x":         ["08:00", "12:00", "17:00", "22:00"],
        "linkedin":  ["08:00", "12:00", "17:00"],
        "telegram":  ["10:00", "16:00", "20:00"],
    }

    def __init__(self) -> None:
        super().__init__()
        # platform -> account_id -> hour -> list[engagement]
        self._stats: Dict[str, Dict[str, Dict[int, List[float]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        # platform -> account_id -> best_hour
        self._best_times: Dict[str, Dict[str, int]] = defaultdict(dict)

    def run(self, action: str = "best_times", **kwargs: Any) -> Any:
        if action == "ingest":
            return self.ingest(kwargs["records"])
        return self.best_times(kwargs.get("platform", "instagram"),
                                top_k=int(kwargs.get("top_k", 4)))

    def track_engagement(self, post_id: str, published_at: str, engagement_rate: float,
                        platform: str, account_id: str) -> None:
        """Store performance per hour/day"""
        try:
            ts = dt.datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
            hour = ts.hour
            self._stats[platform][account_id][hour].append(engagement_rate)
        except Exception as e:
            self.logger.warning(f"Failed to track engagement for post {post_id}: {e}")

    def predict_best_time(self, platform: str, account_id: str, timezone: str = "UTC") -> Dict[str, Any]:
        """Return optimal hour based on historical data"""
        account_stats = self._stats.get(platform, {}).get(account_id, {})

        if not account_stats:
            # Fall back to platform defaults
            default_times = self.DEFAULT_TIMES.get(platform, ["09:00", "12:00", "18:00", "21:00"])
            return {
                "platform": platform,
                "account_id": account_id,
                "best_hour": None,
                "best_time_local": default_times[0],
                "timezone": timezone,
                "source": "default",
                "confidence": 0.0
            }

        # Calculate average engagement per hour
        hour_performance = {}
        for hour, rates in account_stats.items():
            if rates:
                avg_engagement = sum(rates) / len(rates)
                hour_performance[hour] = {
                    "avg_engagement": avg_engagement,
                    "sample_count": len(rates)
                }

        if not hour_performance:
            default_times = self.DEFAULT_TIMES.get(platform, ["09:00", "12:00", "18:00", "21:00"])
            return {
                "platform": platform,
                "account_id": account_id,
                "best_hour": None,
                "best_time_local": default_times[0],
                "timezone": timezone,
                "source": "default",
                "confidence": 0.0
            }

        # Find best hour
        best_hour = max(hour_performance.items(), key=lambda x: x[1]["avg_engagement"])
        best_data = best_hour[1]

        # Convert UTC hour to local time
        local_hour = (best_hour[0] + self._timezone_offset(timezone)) % 24
        local_time = f"{local_hour:02d}:00"

        return {
            "platform": platform,
            "account_id": account_id,
            "best_hour": best_hour[0],
            "best_time_local": local_time,
            "timezone": timezone,
            "avg_engagement": round(best_data["avg_engagement"], 4),
            "sample_count": best_data["sample_count"],
            "source": "learned",
            "confidence": min(1.0, best_data["sample_count"] / 10.0)  # Simple confidence based on sample size
        }

    def auto_update_scheduler(self) -> Dict[str, Any]:
        """Modify Celery schedule dynamically"""
        # This would integrate with Celery Beat to update schedules
        # For now, return current best times for all accounts
        updates = {}

        for platform, accounts in self._stats.items():
            for account_id, hours in accounts.items():
                if hours:
                    best_time = self.predict_best_time(platform, account_id)
                    updates[f"{platform}_{account_id}"] = {
                        "best_time": best_time["best_time_local"],
                        "avg_engagement": best_time["avg_engagement"],
                        "confidence": best_time["confidence"]
                    }

        return {
            "scheduler_updates": updates,
            "total_accounts": sum(len(accounts) for accounts in self._stats.values()),
            "note": "Integration with Celery Beat would apply these schedules automatically"
        }

    def _timezone_offset(self, timezone: str) -> int:
        """Simple timezone offset calculator (basic implementation)"""
        offsets = {
            "UTC": 0,
            "EST": -5,
            "PST": -8,
            "GMT": 0,
            "CET": 1,
            "JST": 9,
            "IST": 5.5,
        }
        return int(offsets.get(timezone.upper(), 0))

    def ingest(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Each record: {platform, account_id, published_at: ISO, engagement: float}"""
        n = 0
        for r in records:
            try:
                account_id = r.get("account_id", "default")
                self.track_engagement(
                    post_id=r.get("post_id", f"unknown_{n}"),
                    published_at=r["published_at"],
                    engagement_rate=float(r.get("engagement") or 0),
                    platform=r["platform"],
                    account_id=account_id
                )
                n += 1
            except Exception as e:
                self.logger.warning(f"Failed to ingest record: {e}")
                continue
        return {"ingested": n}

    def best_times(self, platform: str, top_k: int = 4) -> Dict[str, Any]:
        # For backward compatibility, return platform-level defaults
        return {"platform": platform, "times": self.DEFAULT_TIMES.get(
            platform, ["09:00", "13:00", "20:00"]), "source": "default"}


class SkipAnalysisEngine(BaseEngine):
    name = "skip_analysis"
    description = "Learn skip patterns and optimize content hooks"

    def __init__(self) -> None:
        super().__init__()
        # post_id -> list of skip events
        self._skip_events: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        # platform -> skip_time -> count
        self._patterns: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        # category -> hook effectiveness scores
        self._hook_scores: Dict[str, Dict[str, float]] = defaultdict(dict)

    def track_skip(self, post_id: str, skip_time_seconds: float, platform: str,
                   category: str = "general") -> None:
        """Store skip event: 3s, 10s, 30s"""
        event = {
            "post_id": post_id,
            "skip_time": skip_time_seconds,
            "platform": platform,
            "category": category,
            "timestamp": dt.datetime.utcnow(),
        }
        self._skip_events[post_id].append(event)

        # Update pattern counts (bucket by 5-second intervals)
        bucket = int(skip_time_seconds // 5) * 5
        self._patterns[platform][bucket] += 1

    def analyze_patterns(self, category: Optional[str] = None) -> Dict[str, Any]:
        """Return which hooks/pacing reduce skips"""
        if category:
            # Filter events by category
            relevant_events = []
            for events in self._skip_events.values():
                relevant_events.extend([e for e in events if e.get("category") == category])
        else:
            relevant_events = [e for events in self._skip_events.values() for e in events]

        if not relevant_events:
            return {"insufficient_data": True}

        # Analyze skip patterns by platform
        platform_analysis = {}
        for platform in set(e["platform"] for e in relevant_events):
            platform_events = [e for e in relevant_events if e["platform"] == platform]
            skip_times = [e["skip_time"] for e in platform_events]

            # Find most common skip points
            buckets = {}
            for time in skip_times:
                bucket = int(time // 5) * 5
                buckets[bucket] = buckets.get(bucket, 0) + 1

            most_common_skip = max(buckets.items(), key=lambda x: x[1]) if buckets else (0, 0)

            # Calculate average skip time
            avg_skip = sum(skip_times) / len(skip_times)

            platform_analysis[platform] = {
                "total_skips": len(platform_events),
                "avg_skip_time": round(avg_skip, 2),
                "most_common_skip_bucket": f"{most_common_skip[0]}-{most_common_skip[0]+5}s",
                "skip_count_at_bucket": most_common_skip[1],
                "recommendation": self._get_skip_recommendation(avg_skip, most_common_skip[0])
            }

        return {
            "total_events": len(relevant_events),
            "category": category,
            "platform_analysis": platform_analysis,
            "hook_effectiveness": dict(self._hook_scores.get(category or "general", {}))
        }

    def update_templates(self) -> Dict[str, Any]:
        """Auto-update hook generation based on skip patterns"""
        # Analyze which categories have good vs bad skip patterns
        category_performance = {}

        for category in set(e.get("category", "general") for events in self._skip_events.values() for e in events):
            category_events = [e for events in self._skip_events.values()
                             for e in events if e.get("category") == category]

            if not category_events:
                continue

            skip_times = [e["skip_time"] for e in category_events]
            avg_skip = sum(skip_times) / len(skip_times)

            # Higher average skip time = better (people watch longer)
            category_performance[category] = avg_skip

        # Update hook scores based on performance
        if category_performance:
            best_category = max(category_performance.items(), key=lambda x: x[1])
            worst_category = min(category_performance.items(), key=lambda x: x[1])

            # Boost scores for categories with longer watch times
            for cat, score in category_performance.items():
                normalized_score = score / max(category_performance.values())
                self._hook_scores[cat]["overall_effectiveness"] = normalized_score

        return {
            "categories_analyzed": len(category_performance),
            "best_performing_category": best_category[0] if category_performance else None,
            "worst_performing_category": worst_category[0] if category_performance else None,
            "updated_hook_scores": dict(self._hook_scores)
        }

    def _get_skip_recommendation(self, avg_skip: float, common_skip_bucket: int) -> str:
        """Generate recommendation based on skip patterns"""
        if avg_skip < 5:
            return "Critical: Hooks failing immediately. Rewrite opening 3 seconds."
        elif avg_skip < 15:
            return "Poor: Early dropout. Strengthen hook and first 10 seconds."
        elif common_skip_bucket < 10:
            return "Fair: Early skips common. Test different hook styles."
        elif avg_skip > 25:
            return "Good: People watching through. Maintain current approach."
        else:
            return "Average: Some early skips. Optimize pacing around 15-20s mark."


class ContentFreshnessEngine(BaseEngine):
    name = "content_freshness"
    description = "Track topic recency and recommend rotation"

    def __init__(self) -> None:
        super().__init__()
        self._last_used: Dict[str, dt.datetime] = {}

    def mark_used(self, topic: str) -> None:
        self._last_used[topic.lower().strip()] = dt.datetime.utcnow()

    def run(self, *, topic: str, cooldown_days: int = 7) -> Dict[str, Any]:
        key = topic.lower().strip()
        now = dt.datetime.utcnow()
        last = self._last_used.get(key)
        if not last:
            return {"topic": topic, "fresh": True, "days_since": None,
                    "recommendation": "OK to publish"}
        days = (now - last).days
        fresh = days >= cooldown_days
        return {"topic": topic, "fresh": fresh, "days_since": days,
                "cooldown_days": cooldown_days,
                "recommendation": "OK to publish" if fresh
                                  else f"Wait {cooldown_days - days} more days"}


class ContentDecayEngine(BaseEngine):
    name = "content_decay"
    description = "Model post-publish engagement decay"

    def run(self, *, hours_since_publish: float,
            initial_engagement: float = 1.0,
            half_life_hours: float = 18.0) -> Dict[str, Any]:
        """Exponential decay model: e(t) = e0 * 0.5^(t / half_life)."""
        decay_factor = 0.5 ** (max(0.0, hours_since_publish) / max(1e-3, half_life_hours))
        current = initial_engagement * decay_factor
        return {
            "hours_since_publish": hours_since_publish,
            "half_life_hours": half_life_hours,
            "current_engagement_estimate": round(current, 6),
            "decay_factor": round(decay_factor, 6),
            "recommendation": (
                "Boost or repost" if decay_factor < 0.25 else
                "Engage in comments to extend reach" if decay_factor < 0.5 else
                "Still gaining — leave it"
            ),
        }
