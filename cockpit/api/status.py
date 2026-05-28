"""Cockpit API — /status payload builder.

Returns system health summary using live singletons. Called by
ui/cockpit_routes.py — not a FastAPI router itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from system.autonomy import get_autonomy
from system.fast_risk_cache import get_risk_cache

__all__ = ["status_payload"]


def status_payload() -> dict[str, Any]:
    rc = get_risk_cache().get()
    autonomy_mode = get_autonomy().mode()   # mode() is a method, not a property

    overall = "HALTED"
    if rc.trading_allowed and not rc.safe_mode:
        overall = "HEALTHY"
    elif rc.safe_mode:
        overall = "DEGRADED"

    return {
        "overall": overall,
        "trading_allowed": rc.trading_allowed,
        "safe_mode": rc.safe_mode,
        "kill_switch_active": not rc.trading_allowed,
        "autonomy_mode": autonomy_mode,
        "risk_version": rc.version_id,
        "circuit_breaker_drawdown": rc.circuit_breaker_drawdown,
        "circuit_breaker_loss_pct": rc.circuit_breaker_loss_pct,
    }
