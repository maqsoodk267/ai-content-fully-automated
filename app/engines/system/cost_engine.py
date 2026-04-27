"""
CostEngine — API usage tracking and budget management.

Tracks costs for various AI services, enforces budget limits,
and provides detailed usage reports for billing and optimization.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.engines.base import BaseEngine


class CostEngine(BaseEngine):
    name = "cost"
    description = "API cost tracking and budget management"

    def __init__(self) -> None:
        super().__init__()
        # Cost tracking: user_id -> service -> period -> cost
        self._usage: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(float))
        )

        # Budget limits: user_id -> limit
        self._budgets: Dict[str, float] = {}

        # Service rates (per call, in USD)
        self._service_rates = {
            "openai": 0.002,      # GPT-3.5 per token
            "anthropic": 0.003,   # Claude per token
            "stability": 0.02,    # Stable Diffusion per image
            "elevenlabs": 0.15,   # Text-to-speech per minute
            "replicate": 0.005,   # General AI inference
            "huggingface": 0.0005,# Hosted inference
            "coqui": 0.0,         # Local TTS (free)
            "ffmpeg": 0.0,        # Local processing (free)
        }

        # Period definitions
        self._periods = {
            "daily": lambda d: d.strftime("%Y-%m-%d"),
            "weekly": lambda d: f"{d.year}-W{d.isocalendar().week}",
            "monthly": lambda d: d.strftime("%Y-%m"),
            "yearly": lambda d: d.strftime("%Y"),
        }

    def track_api_call(self, service: str, cost: float, user_id: str = "system",
                      metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Track an API call and its cost.

        Args:
            service: Service name (e.g., 'openai', 'anthropic')
            cost: Cost in USD
            user_id: User identifier
            metadata: Optional metadata about the call

        Returns:
            Dict with tracking confirmation
        """
        now = dt.datetime.utcnow()

        # Track by all periods
        for period_name, period_func in self._periods.items():
            period_key = period_func(now)
            self._usage[user_id][service][f"{period_name}:{period_key}"] += cost

        # Also track total lifetime
        self._usage[user_id][service]["lifetime"] += cost

        return {
            "tracked": True,
            "service": service,
            "cost": cost,
            "user_id": user_id,
            "timestamp": now.isoformat(),
            "metadata": metadata or {},
        }

    def check_budget(self, user_id: str, budget_limit: float,
                    period: str = "monthly") -> Dict[str, Any]:
        """
        Check if user is within budget limit.

        Args:
            user_id: User identifier
            budget_limit: Budget limit in USD
            period: Time period to check

        Returns:
            Dict with budget status
        """
        current_usage = self.get_usage(user_id, period)
        total_cost = current_usage.get("total_cost", 0.0)

        within_budget = total_cost < budget_limit
        remaining = budget_limit - total_cost

        return {
            "user_id": user_id,
            "period": period,
            "budget_limit": budget_limit,
            "current_usage": total_cost,
            "remaining_budget": max(0, remaining),
            "within_budget": within_budget,
            "over_budget_by": max(0, total_cost - budget_limit),
            "usage_percentage": (total_cost / budget_limit * 100) if budget_limit > 0 else 0,
        }

    def set_budget(self, user_id: str, budget_limit: float) -> Dict[str, Any]:
        """
        Set budget limit for a user.

        Args:
            user_id: User identifier
            budget_limit: Budget limit in USD

        Returns:
            Dict with confirmation
        """
        self._budgets[user_id] = budget_limit

        return {
            "user_id": user_id,
            "budget_limit": budget_limit,
            "set_at": dt.datetime.utcnow().isoformat(),
        }

    def get_usage_report(self, user_id: Optional[str] = None,
                        period: str = "monthly") -> Dict[str, Any]:
        """
        Get detailed usage report.

        Args:
            user_id: Specific user (None for all users)
            period: Time period

        Returns:
            Dict with usage statistics
        """
        if user_id:
            return self.get_usage(user_id, period)

        # Aggregate across all users
        all_usage = {}
        total_cost = 0.0
        user_count = 0

        for uid in self._usage.keys():
            user_usage = self.get_usage(uid, period)
            all_usage[uid] = user_usage
            total_cost += user_usage.get("total_cost", 0)
            user_count += 1

        return {
            "period": period,
            "total_users": user_count,
            "total_cost": round(total_cost, 4),
            "average_cost_per_user": round(total_cost / user_count, 4) if user_count > 0 else 0,
            "user_breakdown": all_usage,
        }

    def get_usage(self, user_id: str, period: str = "monthly") -> Dict[str, Any]:
        """
        Get usage statistics for a specific user and period.

        Args:
            user_id: User identifier
            period: Time period

        Returns:
            Dict with detailed usage stats
        """
        user_data = self._usage.get(user_id, {})
        now = dt.datetime.utcnow()

        # Get current period key
        if period in self._periods:
            current_period_key = f"{period}:{self._periods[period](now)}"
        else:
            current_period_key = f"monthly:{self._periods['monthly'](now)}"

        # Aggregate costs by service
        service_costs = {}
        total_cost = 0.0

        for service, periods in user_data.items():
            service_total = 0.0
            for period_key, cost in periods.items():
                if period_key == current_period_key or period_key == "lifetime":
                    service_total += cost

            if service_total > 0:
                service_costs[service] = round(service_total, 4)
                total_cost += service_total

        # Calculate efficiency metrics
        call_count = sum(len(periods) for periods in user_data.values())
        avg_cost_per_call = total_cost / call_count if call_count > 0 else 0

        # Most expensive service
        most_expensive = max(service_costs.items(), key=lambda x: x[1]) if service_costs else None

        return {
            "user_id": user_id,
            "period": period,
            "total_cost": round(total_cost, 4),
            "service_breakdown": service_costs,
            "call_count": call_count,
            "avg_cost_per_call": round(avg_cost_per_call, 6),
            "most_expensive_service": most_expensive[0] if most_expensive else None,
            "budget_limit": self._budgets.get(user_id),
            "budget_status": self.check_budget(user_id, self._budgets.get(user_id, float('inf')), period),
        }

    def estimate_cost(self, service: str, operation: str,
                     params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Estimate cost for a potential operation.

        Args:
            service: Service name
            operation: Operation type
            params: Operation parameters

        Returns:
            Dict with cost estimate
        """
        base_rate = self._service_rates.get(service, 0.001)

        # Operation-specific multipliers
        multipliers = {
            "text_generation": {"per_token": 1.0, "base": 0.01},
            "image_generation": {"per_image": 1.0, "base": 0.02},
            "speech_synthesis": {"per_minute": 1.0, "base": 0.10},
            "translation": {"per_token": 0.5, "base": 0.005},
            "moderation": {"per_token": 0.1, "base": 0.001},
        }

        multiplier = multipliers.get(operation, {"base": base_rate})

        estimated_cost = multiplier.get("base", base_rate)

        # Add parameter-based costs
        if params:
            if "tokens" in params:
                token_cost = params["tokens"] * multiplier.get("per_token", 0.001)
                estimated_cost += token_cost
            if "images" in params:
                image_cost = params["images"] * multiplier.get("per_image", 0.02)
                estimated_cost += image_cost
            if "minutes" in params:
                minute_cost = params["minutes"] * multiplier.get("per_minute", 0.15)
                estimated_cost += minute_cost

        return {
            "service": service,
            "operation": operation,
            "estimated_cost": round(estimated_cost, 6),
            "rate_used": base_rate,
            "parameters": params,
        }

    def get_cost_alerts(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get cost alerts for a user.

        Args:
            user_id: User identifier

        Returns:
            List of alert dictionaries
        """
        alerts = []
        budget_limit = self._budgets.get(user_id)

        if budget_limit:
            budget_status = self.check_budget(user_id, budget_limit)

            if budget_status["usage_percentage"] > 90:
                alerts.append({
                    "type": "budget_warning",
                    "severity": "high",
                    "message": f"Budget usage at {budget_status['usage_percentage']:.1f}%",
                    "remaining": budget_status["remaining_budget"],
                })
            elif budget_status["usage_percentage"] > 75:
                alerts.append({
                    "type": "budget_warning",
                    "severity": "medium",
                    "message": f"Budget usage at {budget_status['usage_percentage']:.1f}%",
                    "remaining": budget_status["remaining_budget"],
                })

        # Check for unusually high daily spending
        daily_usage = self.get_usage(user_id, "daily")
        if daily_usage["total_cost"] > 10.0:  # $10 threshold
            alerts.append({
                "type": "high_usage",
                "severity": "medium",
                "message": f"High daily usage: ${daily_usage['total_cost']:.2f}",
                "period": "daily",
            })

        return alerts

    def reset_usage(self, user_id: str, period: str = "monthly") -> Dict[str, Any]:
        """
        Reset usage counters (for testing or manual reset).

        Args:
            user_id: User identifier
            period: Period to reset

        Returns:
            Dict with reset confirmation
        """
        if user_id in self._usage:
            user_data = self._usage[user_id]

            # Remove period-specific data
            for service in user_data:
                keys_to_remove = []
                for period_key in user_data[service]:
                    if period_key.startswith(f"{period}:"):
                        keys_to_remove.append(period_key)

                for key in keys_to_remove:
                    del user_data[service][key]

        return {
            "user_id": user_id,
            "period": period,
            "reset_at": dt.datetime.utcnow().isoformat(),
        }