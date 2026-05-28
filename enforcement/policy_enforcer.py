"""
enforcement/policy_enforcer.py
Attribute-level policy enforcement: wraps a function call and consults the
risk cache + built-in deny rules before permitting the invocation.

P0.4: self-contained deny rules (martingale, unbounded leverage) replace the
legacy ``governance.policy_engine`` import so enforcement reads from a single
policy surface rather than a separate, unsynchronized legacy singleton.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from system.fast_risk_cache import get_risk_cache


@dataclass(frozen=True)
class EnforceResult:
    allowed: bool
    reason: str
    reasons: tuple[str, ...] = ()


# Built-in deny predicates (previously lived in governance.policy_engine).
_DENY_RULES: tuple[tuple[str, Callable[[dict[str, Any]], bool], str], ...] = (
    (
        "deny_martingale",
        lambda ctx: str(ctx.get("strategy", "")).lower() == "martingale",
        "martingale_forbidden_axiom",
    ),
    (
        "deny_unbounded_leverage",
        lambda ctx: float(ctx.get("leverage", 0.0)) > 10.0,
        "unbounded_leverage_forbidden_axiom",
    ),
)


class PolicyEnforcer:
    def allow(self, ctx: dict[str, Any]) -> EnforceResult:
        rc = get_risk_cache().get()
        if not rc.trading_allowed:
            return EnforceResult(False, "trading_disallowed")
        size_usd = float(ctx.get("size_usd", 0.0))
        portfolio_usd = float(ctx.get("portfolio_usd", 100_000.0))
        ok, reason = rc.allows_trade(size_usd=size_usd, portfolio_usd=portfolio_usd)
        if not ok:
            return EnforceResult(False, reason)
        reasons: list[str] = []
        for _name, predicate, deny_reason in _DENY_RULES:
            try:
                if predicate(ctx):
                    reasons.append(deny_reason)
            except Exception:
                pass
        if reasons:
            return EnforceResult(False, "policy_denied", tuple(reasons))
        return EnforceResult(True, "ok")

    def enforce(self, fn: Callable[..., Any], ctx: dict[str, Any]) -> Any:
        verdict = self.allow(ctx)
        if not verdict.allowed:
            raise PermissionError(f"policy_denied: {verdict.reason}")
        return fn()


_pe: PolicyEnforcer | None = None
_lock = threading.Lock()


def get_policy_enforcer() -> PolicyEnforcer:
    global _pe
    if _pe is None:
        with _lock:
            if _pe is None:
                _pe = PolicyEnforcer()
    return _pe
