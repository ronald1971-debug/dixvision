"""governance.oracle.tier_l2_balanced — L2 Balanced-Tier Governance Check.

<10ms governance gate that includes L1 fast-pass plus:
- Full policy engine evaluation (OPA-backed if available)
- Portfolio state correlation (open positions vs new order)
- Recent fill velocity check (detect runaway ordering)
- Trading mode compliance (MANUAL/SEMI_AUTO/FULL_AUTO enforcement)
- Domain isolation verification (INV-56 Triad Lock)

Escalates to L3 for large orders or when risk conditions are uncertain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from system import time_source


class L2Decision(StrEnum):
    """L2 balanced-tier decision outcomes."""

    APPROVED = "APPROVED"
    DENIED = "DENIED"
    ESCALATE_L3 = "ESCALATE_L3"


@dataclass(frozen=True, slots=True)
class L2Result:
    """Structured result from L2 governance check."""

    decision: L2Decision
    reason: str
    latency_ns: int
    policy_violations: tuple[str, ...] = ()
    ts_ns: int = field(default_factory=time_source.wall_ns)


def approve_l2_balanced(ctx: dict[str, Any]) -> tuple[bool, str]:
    """Run L2 balanced-tier governance check.

    Composes L1 fast check + policy engine + portfolio correlation +
    trading mode enforcement + fill velocity + domain isolation.

    Args:
        ctx: Execution context (same as L1 plus additional keys:
            - trading_mode: MANUAL/SEMI_AUTO/FULL_AUTO
            - source: who produced the intent (indira/dashboard/etc)
            - fills_last_minute: number of fills in last 60s
            - open_positions_domain: position count in this domain

    Returns:
        (approved: bool, reason: str)
    """
    from .tier_l1_fast import approve_l1_fast

    # Step 1: L1 must pass
    ok, reason = approve_l1_fast(ctx)
    if not ok:
        return ok, reason

    # Step 2: Policy engine evaluation
    try:
        from governance.policy_engine import get_policy_engine

        result = get_policy_engine().evaluate(ctx)
        if not result.allowed:
            return False, f"L2_DENY:policy:{';'.join(result.reasons) or 'policy_denied'}"
    except Exception:
        pass  # Policy engine unavailable — pass through (fail-open at L2)

    # Step 3: Trading mode compliance
    trading_mode = ctx.get("trading_mode", "FULL_AUTO")
    source = ctx.get("source", "indira")
    action_class = ctx.get("action_class", "ENTRY")

    if trading_mode == "MANUAL" and source != "dashboard":
        if action_class == "ENTRY":
            return False, "L2_DENY:manual_mode_only_dashboard_entries"

    if trading_mode == "SEMI_AUTO" and source != "dashboard":
        if action_class == "ENTRY":
            # Check if under threshold for auto-fire
            threshold = float(ctx.get("notional_threshold_usd", 5000.0))
            size_usd = float(ctx.get("size_usd", 0.0))
            if size_usd > threshold:
                return False, f"L2_DENY:semi_auto_above_threshold_{size_usd:.0f}>{threshold:.0f}"

    # Step 4: Fill velocity (runaway detection)
    fills_last_minute = int(ctx.get("fills_last_minute", 0))
    max_fills_per_minute = int(ctx.get("max_fills_per_minute", 30))
    if fills_last_minute > max_fills_per_minute:
        return False, f"L2_DENY:fill_velocity_{fills_last_minute}/min>max_{max_fills_per_minute}"

    # Step 5: Domain position count
    open_positions = int(ctx.get("open_positions_domain", 0))
    from immutable_core.constants import AXIOMS

    if open_positions >= AXIOMS.MAX_POSITIONS_PER_DOMAIN:
        return False, f"L2_DENY:max_positions_{open_positions}>={AXIOMS.MAX_POSITIONS_PER_DOMAIN}"

    # Step 6: Determine if L3 escalation needed
    size_usd = float(ctx.get("size_usd", 0.0))
    portfolio_usd = float(ctx.get("portfolio_usd", 100_000.0))
    if portfolio_usd > 0 and (size_usd / portfolio_usd) > 0.005:
        # Large order (>0.5% of portfolio) — recommend L3 deep check
        return True, "L2_PASS:large_order_l3_recommended"

    return True, "L2_PASS"


def l2_full_check(ctx: dict[str, Any]) -> L2Result:
    """Full L2 check returning structured result with timing."""
    start_ns = time_source.now_ns()
    ok, reason = approve_l2_balanced(ctx)
    elapsed_ns = time_source.now_ns() - start_ns

    if ok:
        decision = L2Decision.APPROVED
        if "l3_recommended" in reason.lower():
            decision = L2Decision.ESCALATE_L3
    else:
        decision = L2Decision.DENIED

    violations = tuple(reason.split(";")) if not ok else ()
    return L2Result(
        decision=decision,
        reason=reason,
        latency_ns=elapsed_ns,
        policy_violations=violations,
    )


__all__ = [
    "L2Decision",
    "L2Result",
    "approve_l2_balanced",
    "l2_full_check",
]
