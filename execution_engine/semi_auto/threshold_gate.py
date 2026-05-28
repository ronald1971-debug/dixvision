"""Semi-auto threshold gate (BUILD-DIRECTIVE §8).

Decides whether an ExecutionIntent in SEMI_AUTO mode requires operator
approval or can auto-fire. The decision tree:

  1. EXIT or RISK_REDUCE → always auto-fire (Indira protects)
  2. ENTRY where notional < threshold AND position_fraction < cap
     AND volatility < cap → auto-fire
  3. ENTRY above any threshold → route to approval queue
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ThresholdVerdict(StrEnum):
    """Outcome of the threshold gate check."""

    AUTO_FIRE = "AUTO_FIRE"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


@dataclass(frozen=True, slots=True)
class ThresholdContext:
    """Contextual data needed for the threshold check."""

    is_exit: bool
    is_risk_reduce: bool
    notional_usd: float
    position_fraction: float
    volatility_zscore: float


def evaluate_threshold(
    context: ThresholdContext,
    *,
    notional_threshold_usd: float,
    position_fraction_cap: float,
    volatility_cap_zscore: float,
) -> ThresholdVerdict:
    """Evaluate whether an intent passes the semi-auto threshold gate.

    Returns:
        ThresholdVerdict.AUTO_FIRE — execute immediately.
        ThresholdVerdict.REQUIRES_APPROVAL — route to approval queue.
    """
    # Exits and risk-reductions always auto-fire
    if context.is_exit or context.is_risk_reduce:
        return ThresholdVerdict.AUTO_FIRE

    # Entry threshold checks
    if context.notional_usd > notional_threshold_usd:
        return ThresholdVerdict.REQUIRES_APPROVAL
    if context.position_fraction > position_fraction_cap:
        return ThresholdVerdict.REQUIRES_APPROVAL
    if context.volatility_zscore > volatility_cap_zscore:
        return ThresholdVerdict.REQUIRES_APPROVAL

    return ThresholdVerdict.AUTO_FIRE
