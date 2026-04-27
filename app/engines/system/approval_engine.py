"""
ApprovalEngine — Automated content approval based on trust scores.

Evaluates content quality, account history, and health metrics to determine
whether content should be auto-approved, sent for review, or rejected.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional

from app.engines.base import BaseEngine


class ApprovalEngine(BaseEngine):
    name = "approval"
    description = "Automated content approval system"

    def __init__(self) -> None:
        super().__init__()
        # Trust score thresholds
        self._auto_approve_threshold = 90.0
        self._review_threshold = 70.0

        # Auto-pilot mode settings
        self._auto_pilot_enabled = False
        self._auto_pilot_accounts: set[str] = set()

        # Quality weights for trust score calculation
        self._quality_weights = {
            "content_quality": 0.4,
            "account_health": 0.3,
            "posting_history": 0.2,
            "engagement_rate": 0.1,
        }

    def calculate_trust_score(self, content: Dict[str, Any]) -> float:
        """
        Calculate trust score (0-100) based on multiple factors.

        Args:
            content: Dict containing content metadata, user info, etc.

        Returns:
            float: Trust score between 0-100
        """
        score = 0.0

        # Content quality score (0-100)
        quality_score = self._calculate_content_quality(content)
        score += quality_score * self._quality_weights["content_quality"]

        # Account health score (0-100)
        account_score = self._calculate_account_health(content)
        score += account_score * self._quality_weights["account_health"]

        # Posting history score (0-100)
        history_score = self._calculate_posting_history(content)
        score += history_score * self._quality_weights["posting_history"]

        # Engagement rate score (0-100)
        engagement_score = self._calculate_engagement_rate(content)
        score += engagement_score * self._quality_weights["engagement_rate"]

        return min(100.0, max(0.0, score))

    def decide_action(self, trust_score: float, account_id: Optional[str] = None) -> str:
        """
        Decide approval action based on trust score.

        Args:
            trust_score: Calculated trust score (0-100)
            account_id: Optional account ID for auto-pilot check

        Returns:
            str: "approve", "review", or "reject"
        """
        # Check auto-pilot mode for high-trust accounts
        if self._auto_pilot_enabled and account_id in self._auto_pilot_accounts:
            return "approve"

        if trust_score >= self._auto_approve_threshold:
            return "approve"
        elif trust_score >= self._review_threshold:
            return "review"
        else:
            return "reject"

    def auto_pilot_mode(self, enabled: bool, account_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Enable/disable auto-pilot mode for accounts.

        Args:
            enabled: Whether to enable auto-pilot
            account_id: Specific account to toggle (None for global setting)

        Returns:
            Dict with current status
        """
        if account_id:
            if enabled:
                self._auto_pilot_accounts.add(account_id)
            else:
                self._auto_pilot_accounts.discard(account_id)
        else:
            self._auto_pilot_enabled = enabled
            if not enabled:
                self._auto_pilot_accounts.clear()

        return {
            "auto_pilot_enabled": self._auto_pilot_enabled,
            "auto_pilot_accounts": list(self._auto_pilot_accounts),
            "auto_approve_threshold": self._auto_approve_threshold,
            "review_threshold": self._review_threshold,
        }

    def evaluate_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Complete content evaluation pipeline.

        Args:
            content: Content metadata dictionary

        Returns:
            Dict with trust score, decision, and reasoning
        """
        trust_score = self.calculate_trust_score(content)
        account_id = content.get("account_id") or content.get("user_id")
        decision = self.decide_action(trust_score, account_id)

        reasoning = self._generate_reasoning(content, trust_score, decision)

        return {
            "trust_score": round(trust_score, 2),
            "decision": decision,
            "reasoning": reasoning,
            "thresholds": {
                "auto_approve": self._auto_approve_threshold,
                "review": self._review_threshold,
            },
            "auto_pilot_active": (
                self._auto_pilot_enabled and
                account_id in self._auto_pilot_accounts
            ),
            "evaluated_at": dt.datetime.utcnow().isoformat(),
        }

    def _calculate_content_quality(self, content: Dict[str, Any]) -> float:
        """Calculate content quality score (0-100)."""
        score = 50.0  # Base score

        # Quality score from content analysis
        if "quality_score" in content:
            score += (content["quality_score"] - 50) * 0.8

        # Script length (prefer substantial content)
        script = content.get("script", "")
        if len(script) > 500:
            score += 10
        elif len(script) < 100:
            score -= 15

        # Has hooks and CTAs
        if content.get("hooks"):
            score += 5
        if content.get("ctas"):
            score += 5

        # Platform optimization
        platforms = content.get("platforms", [])
        if platforms:
            score += min(len(platforms) * 2, 10)

        return min(100.0, max(0.0, score))

    def _calculate_account_health(self, content: Dict[str, Any]) -> float:
        """Calculate account health score (0-100)."""
        score = 50.0  # Base score

        # Account age (prefer established accounts)
        created_at = content.get("account_created_at")
        if created_at:
            try:
                created = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                days_old = (dt.datetime.utcnow() - created).days
                if days_old > 365:
                    score += 20
                elif days_old > 30:
                    score += 10
                elif days_old < 7:
                    score -= 10
            except:
                pass

        # Posting frequency (prefer consistent posting)
        posts_count = content.get("total_posts", 0)
        if posts_count > 100:
            score += 15
        elif posts_count > 10:
            score += 5

        # Account status
        if content.get("is_verified"):
            score += 10
        if content.get("is_active"):
            score += 5

        return min(100.0, max(0.0, score))

    def _calculate_posting_history(self, content: Dict[str, Any]) -> float:
        """Calculate posting history score (0-100)."""
        score = 50.0  # Base score

        # Previous approval rate
        approved_posts = content.get("approved_posts", 0)
        total_posts = content.get("total_posts", 1)
        approval_rate = approved_posts / total_posts

        if approval_rate > 0.9:
            score += 25
        elif approval_rate > 0.7:
            score += 10
        elif approval_rate < 0.5:
            score -= 20

        # Recent performance (last 30 days)
        recent_approved = content.get("recent_approved", 0)
        recent_total = content.get("recent_total", 1)
        recent_rate = recent_approved / recent_total

        if recent_rate > 0.8:
            score += 15
        elif recent_rate < 0.6:
            score -= 15

        return min(100.0, max(0.0, score))

    def _calculate_engagement_rate(self, content: Dict[str, Any]) -> float:
        """Calculate engagement rate score (0-100)."""
        score = 50.0  # Base score

        # Average engagement rate
        avg_engagement = content.get("avg_engagement_rate", 0.0)
        if avg_engagement > 0.1:  # 10%
            score += 20
        elif avg_engagement > 0.05:  # 5%
            score += 10
        elif avg_engagement < 0.01:  # 1%
            score -= 10

        # Virality prediction
        virality = content.get("virality_prediction", 0.0)
        if virality > 80:
            score += 15
        elif virality > 60:
            score += 5

        return min(100.0, max(0.0, score))

    def _generate_reasoning(self, content: Dict[str, Any], trust_score: float,
                           decision: str) -> str:
        """Generate human-readable reasoning for the decision."""
        reasons = []

        if trust_score >= self._auto_approve_threshold:
            reasons.append("High trust score indicates reliable content")
        elif trust_score >= self._review_threshold:
            reasons.append("Moderate trust score requires human review")
        else:
            reasons.append("Low trust score suggests potential issues")

        # Add specific insights
        quality_score = content.get("quality_score", 50)
        if quality_score > 80:
            reasons.append("Content quality is excellent")
        elif quality_score < 40:
            reasons.append("Content quality needs improvement")

        account_age_days = 0
        created_at = content.get("account_created_at")
        if created_at:
            try:
                created = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                account_age_days = (dt.datetime.utcnow() - created).days
            except:
                pass

        if account_age_days > 365:
            reasons.append("Established account with good history")
        elif account_age_days < 30:
            reasons.append("New account requires additional scrutiny")

        return ". ".join(reasons)