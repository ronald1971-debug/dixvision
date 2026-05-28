"""governance.oracle.tier_l1_fast — L1 Fast-Tier Synchronous Approval.

Sub-millisecond governance gate using only precomputed FastRiskCache.
No I/O. No external calls. Pure in-memory decision.

L1 is the first of three oracle tiers:
  L1 (fast): sub-ms, in-memory risk cache only
  L2 (balanced): <10ms, includes portfolio state + recent fills
  L3 (deep): <100ms, full governance evaluation + drift oracle

L1 checks:
1. Position size vs max per-trade limit (AXIOMS.MAX_LOSS_PER_TRADE_FLOOR_PCT)
2. Domain exposure vs per-domain cap (AXIOMS.MAX_DOMAIN_EXPOSURE_PCT)
3. Total exposure vs system-wide cap (AXIOMS.MAX_TOTAL_EXPOSURE_PCT)
4. Order interval throttle (AXIOMS.MIN_ORDER_INTERVAL_MS)
5. Kill switch status (if armed + triggered → deny all)

If L1 passes, order proceeds. If L1 soft-fails, escalate to L2.
If L1 hard-fails, deny immediately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from system import time_source


class L1Decision(StrEnum):
    """L1 fast-tier decision outcomes."""

    APPROVED = "APPROVED"
    DENIED = "DENIED"
    ESCALATE_L2 = "ESCALATE_L2"


@dataclass(frozen=True, slots=True)
class L1Result:
    """Result of an L1 fast-tier governance check."""

    decision: L1Decision
    reason: str
    latency_ns: int
    checks_passed: int
    checks_total: int
    ts_ns: int = field(default_factory=time_source.wall_ns)


def approve_l1_fast(ctx: dict[str, Any]) -> tuple[bool, str]:
    """Run L1 fast-tier governance check against the risk cache.

    This is the hot-path governance gate. Must complete in sub-millisecond.
    No I/O. No locks. Pure computation from precomputed cache values.

    Args:
        ctx: Execution context with keys:
            - size_usd: Order notional value
            - portfolio_usd: Total portfolio value
            - domain: Trading domain (NORMAL/COPY_TRADING/MEMECOIN)
            - domain_exposure_usd: Current exposure in this domain
            - total_exposure_usd: Total exposure across all domains
            - last_order_ts_ns: Timestamp of last order in this domain
            - side: BUY or SELL (exits always pass)

    Returns:
        (approved: bool, reason: str)
    """
    start_ns = time_source.now_ns()

    from system.fast_risk_cache import get_risk_cache

    rc = get_risk_cache().get()

    size_usd = float(ctx.get("size_usd", 0.0))
    portfolio_usd = float(ctx.get("portfolio_usd", 100_000.0))
    domain_exposure = float(ctx.get("domain_exposure_usd", 0.0))
    total_exposure = float(ctx.get("total_exposure_usd", 0.0))
    last_order_ns = int(ctx.get("last_order_ts_ns", 0))
    side = str(ctx.get("side", "BUY"))

    # Exits always pass L1 (risk reductions are always allowed)
    if side == "SELL" or ctx.get("action_class") in ("EXIT", "RISK_REDUCE"):
        return True, "L1_PASS:exit_always_allowed"

    # Check 1: Kill switch
    if getattr(rc, "kill_switch_active", False):
        return False, "L1_DENY:kill_switch_active"

    # Check 2: Per-trade size limit
    if portfolio_usd > 0:
        trade_pct = (size_usd / portfolio_usd) * 100
        from immutable_core.constants import AXIOMS

        if trade_pct > AXIOMS.MAX_LOSS_PER_TRADE_FLOOR_PCT:
            return (
                False,
                f"L1_DENY:trade_size_{trade_pct:.2f}%>max_{AXIOMS.MAX_LOSS_PER_TRADE_FLOOR_PCT}%",
            )

    # Check 3: Domain exposure cap
    if portfolio_usd > 0:
        domain_pct = ((domain_exposure + size_usd) / portfolio_usd) * 100
        if domain_pct > AXIOMS.MAX_DOMAIN_EXPOSURE_PCT:
            return (
                False,
                f"L1_DENY:domain_exposure_{domain_pct:.1f}%>cap_{AXIOMS.MAX_DOMAIN_EXPOSURE_PCT}%",
            )

    # Check 4: Total exposure cap
    if portfolio_usd > 0:
        total_pct = ((total_exposure + size_usd) / portfolio_usd) * 100
        if total_pct > AXIOMS.MAX_TOTAL_EXPOSURE_PCT:
            return (
                False,
                f"L1_DENY:total_exposure_{total_pct:.1f}%>cap_{AXIOMS.MAX_TOTAL_EXPOSURE_PCT}%",
            )

    # Check 5: Order interval throttle
    if last_order_ns > 0:
        elapsed_ms = (time_source.now_ns() - last_order_ns) / 1_000_000
        if elapsed_ms < AXIOMS.MIN_ORDER_INTERVAL_MS:
            return (
                False,
                f"L1_DENY:order_throttle_{elapsed_ms:.1f}ms<min_{AXIOMS.MIN_ORDER_INTERVAL_MS}ms",
            )

    # Check 6: FastRiskCache allows_trade (composite check)
    ok, reason = rc.allows_trade(
        size_usd=size_usd,
        portfolio_usd=portfolio_usd,
    )
    if not ok:
        return False, f"L1_DENY:risk_cache:{reason}"

    elapsed_ns = time_source.now_ns() - start_ns
    if elapsed_ns > 1_000_000:  # > 1ms = escalate
        return True, f"L1_PASS:slow_{elapsed_ns / 1000:.0f}us_escalate_recommended"

    return True, "L1_PASS"


def l1_full_check(ctx: dict[str, Any]) -> L1Result:
    """Full L1 check returning structured result with timing."""
    start_ns = time_source.now_ns()
    ok, reason = approve_l1_fast(ctx)
    elapsed_ns = time_source.now_ns() - start_ns

    if ok:
        decision = L1Decision.APPROVED
        if "escalate" in reason.lower():
            decision = L1Decision.ESCALATE_L2
    else:
        decision = L1Decision.DENIED

    return L1Result(
        decision=decision,
        reason=reason,
        latency_ns=elapsed_ns,
        checks_passed=6 if ok else 0,
        checks_total=6,
    )


__all__ = [
    "L1Decision",
    "L1Result",
    "approve_l1_fast",
    "l1_full_check",
]
