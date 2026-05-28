"""SE-01 — game-theoretic order placement.

Determines optimal order placement accounting for adversarial
market-maker behaviour. Pure computation. INV-15. B1.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["AdversarialPlan", "AdversarialExecutor"]


@dataclass(frozen=True, slots=True)
class AdversarialPlan:
    symbol: str
    ts_ns: int
    recommended_side: str       # "BUY" or "SELL"
    limit_offset_bps: float     # how far from mid to place limit (bps)
    order_type: str             # "LIMIT" or "MARKET"
    urgency: float              # 0.0 = patient, 1.0 = immediate
    rationale: str = ""


class AdversarialExecutor:
    """Generate adversarial-aware execution plans.

    Uses spread and crowding information to recommend whether to
    use aggressive market orders or patient limit orders.
    """

    def __init__(
        self,
        aggression_threshold: float = 0.7,
        max_limit_offset_bps: float = 5.0,
    ) -> None:
        self._aggression_thresh = aggression_threshold
        self._max_offset = max_limit_offset_bps

    def plan(
        self,
        symbol: str,
        ts_ns: int,
        *,
        side: str,
        urgency: float,
        spread_bps: float,
        crowding_score: float,
    ) -> AdversarialPlan:
        if urgency >= self._aggression_thresh or crowding_score >= 0.8:
            order_type = "MARKET"
            offset = 0.0
            rationale = f"aggressive: urgency={urgency:.2f} crowding={crowding_score:.2f}"
        else:
            order_type = "LIMIT"
            offset = min(self._max_offset, spread_bps * 0.3 * (1.0 - urgency))
            rationale = f"patient limit: spread={spread_bps:.1f}bps offset={offset:.1f}bps"

        return AdversarialPlan(
            symbol=symbol, ts_ns=ts_ns,
            recommended_side=side,
            limit_offset_bps=offset,
            order_type=order_type,
            urgency=urgency,
            rationale=rationale,
        )
