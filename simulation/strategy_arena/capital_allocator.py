"""simulation/strategy_arena/capital_allocator.py
DIX VISION v42.2 — Simulation Capital Allocator

Allocates simulated capital across strategies within the strategy arena.
Mirrors the production CapitalScheduler logic but operates on simulation
state rather than live portfolio state.

Pure functions + frozen dataclasses (INV-15). No IO.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_REGIME_MULTIPLIERS: dict[str, float] = {
    "TREND_UP":   1.2,
    "TREND_DOWN": 1.2,
    "RANGE":      0.8,
    "VOL_SPIKE":  0.4,
    "UNKNOWN":    1.0,
}

_FLOOR_PCT = 0.02
_CAP_PCT = 0.40


@dataclass(frozen=True, slots=True)
class SimAllocationRequest:
    """Capital allocation request for one simulation strategy."""
    strategy_id: str
    regime: str
    score: float     # composite score from scoring_engine
    priority: int = 1


@dataclass(frozen=True, slots=True)
class SimAllocationDecision:
    """Resolved capital allocation in a simulation."""
    strategy_id: str
    allocated_usd: float
    allocation_fraction: float
    regime_multiplier: float
    reason: str


def allocate_sim_capital(
    requests: list[SimAllocationRequest],
    total_capital_usd: float = 100_000.0,
) -> list[SimAllocationDecision]:
    """
    Allocate simulation capital across strategies.

    Uses score-weighted proportional allocation with regime multipliers,
    floor (2%), and cap (40%).
    """
    if not requests or total_capital_usd <= 0:
        return []

    floor_usd = total_capital_usd * _FLOOR_PCT
    cap_usd = total_capital_usd * _CAP_PCT

    weighted: list[tuple[SimAllocationRequest, float]] = []
    for req in requests:
        mult = _REGIME_MULTIPLIERS.get(req.regime.upper(), 1.0)
        weight = max(0.0, req.score) * mult * req.priority
        weighted.append((req, weight))

    total_weight = sum(w for _, w in weighted)
    if total_weight <= 0:
        equal = total_capital_usd / len(requests)
        return [
            SimAllocationDecision(
                strategy_id=req.strategy_id,
                allocated_usd=min(equal, cap_usd),
                allocation_fraction=min(equal, cap_usd) / total_capital_usd,
                regime_multiplier=_REGIME_MULTIPLIERS.get(req.regime.upper(), 1.0),
                reason="equal_split_fallback",
            )
            for req, _ in weighted
        ]

    decisions: list[SimAllocationDecision] = []
    for req, weight in weighted:
        raw = (weight / total_weight) * total_capital_usd
        allocated = max(floor_usd, min(raw, cap_usd))
        mult = _REGIME_MULTIPLIERS.get(req.regime.upper(), 1.0)
        decisions.append(
            SimAllocationDecision(
                strategy_id=req.strategy_id,
                allocated_usd=allocated,
                allocation_fraction=allocated / total_capital_usd,
                regime_multiplier=mult,
                reason=f"score_weighted regime={req.regime}",
            )
        )
    return decisions


__all__ = [
    "SimAllocationDecision",
    "SimAllocationRequest",
    "allocate_sim_capital",
]
