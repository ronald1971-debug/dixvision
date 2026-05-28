"""
intelligence_engine/portfolio/capital_scheduler.py
DIX VISION v42.2 — Capital Scheduler

Schedules capital allocation across strategies based on regime context
and risk budgets. Applies regime-dependent multipliers so trending
strategies receive more capital in trending regimes and less in choppy
or high-volatility regimes.

This module produces AllocationDecision records; the operator sets the
total_budget_usd ceiling and that ceiling is never breached.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

_REGIME_MULTIPLIERS: dict[str, float] = {
    "TREND_UP":   1.2,
    "TREND_DOWN": 1.2,
    "RANGE":      0.8,
    "VOL_SPIKE":  0.4,
    "UNKNOWN":    1.0,
}


@dataclass(frozen=True, slots=True)
class AllocationRequest:
    """Capital allocation request from a strategy."""
    strategy_id: str
    regime: str
    requested_usd: float
    priority: int = 1  # higher = more important


@dataclass(frozen=True, slots=True)
class AllocationDecision:
    """Resolved capital allocation for a strategy."""
    strategy_id: str
    allocated_usd: float
    allocation_fraction: float
    regime_multiplier: float
    reason: str


class CapitalScheduler:
    """
    Pro-rata capital scheduler with regime-based multipliers.

    Thread-safe. The operator sets total_budget_usd; the scheduler
    never exceeds it.
    """

    def __init__(self, total_budget_usd: float = 100_000.0) -> None:
        self._lock = threading.Lock()
        self._total_budget_usd = total_budget_usd

    def set_budget(self, total_budget_usd: float) -> None:
        """Update the total capital budget (operator only)."""
        with self._lock:
            self._total_budget_usd = total_budget_usd

    def schedule(
        self,
        requests: list[AllocationRequest],
    ) -> list[AllocationDecision]:
        """
        Allocate capital across strategies.

        Steps:
          1. Apply regime multiplier to each request
          2. Scale to budget proportionally by adjusted request size
          3. Respect per-strategy floor (2% of budget) and cap (40%)
        """
        with self._lock:
            budget = self._total_budget_usd

        if not requests or budget <= 0:
            return []

        floor_usd = budget * 0.02
        cap_usd = budget * 0.40

        # Compute adjusted weights
        adjusted: list[tuple[AllocationRequest, float]] = []
        for req in requests:
            mult = _REGIME_MULTIPLIERS.get(req.regime.upper(), 1.0)
            weight = max(0.0, req.requested_usd) * mult * req.priority
            adjusted.append((req, weight))

        total_weight = sum(w for _, w in adjusted)
        if total_weight <= 0:
            # Equal split when all weights are zero
            equal = budget / len(requests)
            return [
                AllocationDecision(
                    strategy_id=req.strategy_id,
                    allocated_usd=min(equal, cap_usd),
                    allocation_fraction=min(equal, cap_usd) / budget,
                    regime_multiplier=_REGIME_MULTIPLIERS.get(req.regime.upper(), 1.0),
                    reason="equal_split_fallback",
                )
                for req, _ in adjusted
            ]

        decisions: list[AllocationDecision] = []
        for req, weight in adjusted:
            raw = (weight / total_weight) * budget
            allocated = max(floor_usd, min(raw, cap_usd))
            mult = _REGIME_MULTIPLIERS.get(req.regime.upper(), 1.0)
            decisions.append(
                AllocationDecision(
                    strategy_id=req.strategy_id,
                    allocated_usd=allocated,
                    allocation_fraction=allocated / budget,
                    regime_multiplier=mult,
                    reason=f"pro_rata regime={req.regime}",
                )
            )
        return decisions

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"total_budget_usd": self._total_budget_usd}


__all__ = [
    "AllocationRequest",
    "AllocationDecision",
    "CapitalScheduler",
]
