"""
HashtagLearningEngine — learns which hashtags drive impressions/engagement
from the analytics records and recommends the next batch to use.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.engines.base import BaseEngine


class HashtagLearningEngine(BaseEngine):
    name = "hashtag_learning"
    description = "Learn winning hashtags and recommend optimal sets"

    def __init__(self) -> None:
        super().__init__()
        # tag -> platform -> category -> dict(uses, impressions, engagement)
        self._stats: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(
                lambda: {"uses": 0, "impressions": 0.0, "engagement": 0.0}
            ))
        )

    def run(
        self,
        action: str = "recommend",
        **kwargs: Any,
    ) -> Any:
        if action == "ingest":
            return self.ingest(kwargs["records"])
        if action == "recommend":
            return self.recommend(
                seed_topic=kwargs.get("topic"),
                desired=int(kwargs.get("count", 12)),
                niche_pool=kwargs.get("niche_pool"),
            )
        if action == "stats":
            return self.snapshot()
        raise ValueError("action must be ingest|recommend|stats")

    def track_performance(self, hashtags: List[str], impressions: float, engagement: float,
                         platform: str = "general", category: str = "general") -> None:
        """Store hashtag metrics"""
        for tag in hashtags:
            clean_tag = tag.lstrip("#").lower()
            if not clean_tag:
                continue
            stats = self._stats[clean_tag][platform][category]
            stats["uses"] += 1
            stats["impressions"] += impressions
            stats["engagement"] += engagement

    def recommend_hashtags(self, category: str, platform: str, count: int = 10) -> List[str]:
        """Return top-performing hashtags"""
        candidates = {}

        # Get hashtags for this category and platform
        for tag, platforms in self._stats.items():
            if platform in platforms and category in platforms[platform]:
                stats = platforms[platform][category]
                uses = max(1, stats["uses"])
                ipu = stats["impressions"] / uses  # impressions per use
                epu = stats["engagement"] / uses   # engagement per use
                score = (ipu * 0.4) + (epu * 60.0) + min(uses, 20) * 0.5
                candidates[tag] = score

        # Also include general category hashtags as fallback
        if category != "general":
            for tag, platforms in self._stats.items():
                if platform in platforms and "general" in platforms[platform]:
                    stats = platforms[platform]["general"]
                    uses = max(1, stats["uses"])
                    ipu = stats["impressions"] / uses
                    epu = stats["engagement"] / uses
                    score = (ipu * 0.3) + (epu * 40.0) + min(uses, 15) * 0.3
                    candidates[tag] = candidates.get(tag, 0) + score

        # Rank and return top hashtags
        ranked = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
        return [f"#{tag}" for tag, _ in ranked[:count]]

    def drop_poor_hashtags(self, threshold_engagement: float = 0.5) -> Dict[str, Any]:
        """Remove underperforming hashtags"""
        removed = []
        kept = []

        for tag in list(self._stats.keys()):
            # Check if any platform/category combination meets the threshold
            keep_tag = False
            for platform, categories in self._stats[tag].items():
                for category, stats in categories.items():
                    uses = max(1, stats["uses"])
                    epu = stats["engagement"] / uses
                    if epu >= threshold_engagement:
                        keep_tag = True
                        break
                if keep_tag:
                    break

            if keep_tag:
                kept.append(tag)
            else:
                del self._stats[tag]
                removed.append(tag)

        return {
            "removed_count": len(removed),
            "kept_count": len(kept),
            "removed_hashtags": removed,
            "threshold": threshold_engagement
        }

    def run(
        self,
        action: str = "recommend",
        **kwargs: Any,
    ) -> Any:
        if action == "ingest":
            return self.ingest(kwargs["records"])
        if action == "recommend":
            return self.recommend(
                seed_topic=kwargs.get("topic"),
                desired=int(kwargs.get("count", 12)),
                niche_pool=kwargs.get("niche_pool"),
            )
        if action == "stats":
            return self.snapshot()
        raise ValueError("action must be ingest|recommend|stats")

    # ------------------------------------------------------------------
    def ingest(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Each record: {hashtags: [...], impressions: int, engagement: float, platform?: str, category?: str}"""
        n = 0
        for r in records:
            hashtags = r.get("hashtags", [])
            impressions = float(r.get("impressions") or 0)
            engagement = float(r.get("engagement") or 0)
            platform = r.get("platform", "general")
            category = r.get("category", "general")

            self.track_performance(hashtags, impressions, engagement, platform, category)
            n += len(hashtags)
        return {"ingested": n, "unique_tags": len(self._stats)}

    def recommend(
        self,
        *,
        seed_topic: Optional[str] = None,
        desired: int = 12,
        niche_pool: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        # For backward compatibility, use general category and platform
        recommended = self.recommend_hashtags("general", "general", desired)

        # Add seeded extras if we don't have enough learned tags
        if len(recommended) < desired:
            for extra in (niche_pool or []):
                t = extra.lstrip("#").lower()
                hashtag = f"#{t}"
                if hashtag not in recommended:
                    recommended.append(hashtag)
                    if len(recommended) >= desired:
                        break

            if seed_topic and len(recommended) < desired:
                seed = seed_topic.lower().replace(" ", "")
                hashtag = f"#{seed}"
                if hashtag not in recommended:
                    recommended.append(hashtag)

        return {"recommended": recommended[:desired], "candidates": len(self._stats)}

    def snapshot(self) -> Dict[str, Any]:
        # Aggregate stats across all platforms and categories
        tag_summary = {}
        for tag, platforms in self._stats.items():
            total_uses = 0
            total_impressions = 0.0
            total_engagement = 0.0

            for platform, categories in platforms.items():
                for category, stats in categories.items():
                    total_uses += stats["uses"]
                    total_impressions += stats["impressions"]
                    total_engagement += stats["engagement"]

            tag_summary[tag] = {
                "uses": total_uses,
                "impressions": total_impressions,
                "engagement": total_engagement
            }

        ranked = sorted(
            ((t, s["uses"], s["impressions"], s["engagement"])
             for t, s in tag_summary.items()),
            key=lambda x: x[3], reverse=True,
        )[:50]
        return {"top_50": [{"tag": f"#{t}", "uses": int(u),
                            "impressions": imp, "engagement": eng}
                           for t, u, imp, eng in ranked]}
