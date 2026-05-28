"""governance.oracle.tier_l3_deep — L3 Deep-Tier Governance Check.

<100ms governance gate used for large orders, strategy deployment approvals,
and periodic rebalance evaluation. Includes:
- Full L2 check (L1 + policy + trading mode + velocity)
- Correlation check against open positions (prevent concentration)
- Drawdown trajectory analysis (predict breach before it happens)
- Drift oracle consultation (is the system diverging?)
- Cross-domain leakage detection (INV-56 Triad Lock verification)
- Consecutive loss tracking (AXIOMS.MAX_CONSECUTIVE_LOSSES)

L3 is asynchronous by design — never used on the hot path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from system import time_source


class L3Decision(StrEnum):
    """L3 deep-tier decision outcomes."""

    APPROVED = "APPROVED"
    DENIED = "DENIED"
    DEFERRED = "DEFERRED"


@dataclass(frozen=True, slots=True)
class L3Result:
    """Structured result from L3 deep governance check."""

    decision: L3Decision
    reason: str
    latency_ns: int
    correlation_score: float = 0.0
    drawdown_trajectory_pct: float = 0.0
    drift_score: float = 0.0
    ts_ns: int = field(default_factory=time_source.wall_ns)


def approve_l3_deep(ctx: dict[str, Any]) -> tuple[bool, str]:
    """Run L3 deep-tier governance check.

    Composes L2 balanced check + correlation + drawdown trajectory +
    drift oracle + cross-domain leakage + consecutive losses.

    Args:
        ctx: Full execution context (L1+L2 keys plus:
            - correlation_to_open: portfolio correlation [0,1]
            - current_exposure_pct: total exposure as fraction
            - drawdown_session_pct: current session drawdown
            - consecutive_losses: number of consecutive losses
            - drift_score: current drift oracle output [0,1]
            - target_domain: which domain this order targets)

    Returns:
        (approved: bool, reason: str)
    """
    from .tier_l2_balanced import approve_l2_balanced

    # Step 1: L2 must pass
    ok, reason = approve_l2_balanced(ctx)
    if not ok:
        return ok, reason

    # Step 2: Exposure check (stricter than L1/L2)
    exposure = float(ctx.get("current_exposure_pct", 0.0))
    if exposure > 0.40:
        return False, f"L3_DENY:exposure_{exposure:.2f}>40pct"

    # Step 3: Correlation check (prevent concentration risk)
    correlation = float(ctx.get("correlation_to_open", 0.0))
    if correlation > 0.85:
        return False, f"L3_DENY:correlation_{correlation:.2f}>85pct"

    # Step 4: Drawdown trajectory analysis
    drawdown = float(ctx.get("drawdown_session_pct", 0.0))
    from immutable_core.constants import AXIOMS

    if drawdown > (AXIOMS.MAX_DRAWDOWN_FLOOR_PCT * 0.75):
        return False, f"L3_DENY:drawdown_trajectory_{drawdown:.2f}%>75%_of_floor"

    # Step 5: Consecutive losses
    consecutive_losses = int(ctx.get("consecutive_losses", 0))
    if consecutive_losses >= AXIOMS.MAX_CONSECUTIVE_LOSSES:
        return (
            False,
            f"L3_DENY:consecutive_losses_{consecutive_losses}>={AXIOMS.MAX_CONSECUTIVE_LOSSES}",
        )

    # Step 6: Drift oracle consultation
    drift_score = float(ctx.get("drift_score", 0.0))
    if drift_score > 0.7:
        return False, f"L3_DENY:drift_score_{drift_score:.2f}>0.7"
    if drift_score > 0.5:
        # High drift but not critical — allow with warning
        return True, f"L3_PASS:elevated_drift_{drift_score:.2f}"

    # Step 7: Cross-domain leakage detection (INV-56)
    target_domain = ctx.get("target_domain", "")
    signal_domain = ctx.get("signal_domain", "")
    if target_domain and signal_domain and target_domain != signal_domain:
        return False, f"L3_DENY:cross_domain_leakage_{signal_domain}→{target_domain}"

    # Step 8: Strategy deployment check (if this is a strategy change)
    if ctx.get("is_strategy_deployment", False):
        sandbox_passes = int(ctx.get("sandbox_passes", 0))
        if sandbox_passes < 3:
            return False, f"L3_DENY:strategy_deployment_insufficient_sandbox_{sandbox_passes}<3"

    return True, "L3_PASS"


def l3_full_check(ctx: dict[str, Any]) -> L3Result:
    """Full L3 check returning structured result with timing and metrics."""
    start_ns = time_source.now_ns()
    ok, reason = approve_l3_deep(ctx)
    elapsed_ns = time_source.now_ns() - start_ns

    decision = L3Decision.APPROVED if ok else L3Decision.DENIED

    return L3Result(
        decision=decision,
        reason=reason,
        latency_ns=elapsed_ns,
        correlation_score=float(ctx.get("correlation_to_open", 0.0)),
        drawdown_trajectory_pct=float(ctx.get("drawdown_session_pct", 0.0)),
        drift_score=float(ctx.get("drift_score", 0.0)),
    )


__all__ = [
    "L3Decision",
    "L3Result",
    "approve_l3_deep",
    "l3_full_check",
]
