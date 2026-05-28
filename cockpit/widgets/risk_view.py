"""Cockpit widget — risk dashboard view.

Pulls from get_risk_cache() and get_arbiter() directly.
No constructor injection required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from system.fast_risk_cache import get_risk_cache

__all__ = ["risk_view_payload"]


def risk_view_payload() -> dict[str, Any]:
    rc = get_risk_cache().get()
    drawdown_pct_used = 0.0
    if rc.circuit_breaker_drawdown and rc.circuit_breaker_drawdown > 0:
        drawdown_pct_used = min(100.0, rc.circuit_breaker_drawdown)

    def _status(pct: float) -> str:
        if pct >= 90:
            return "CRITICAL"
        if pct >= 70:
            return "WARNING"
        return "OK"

    bars = [
        {
            "label": "Drawdown limit",
            "current": rc.circuit_breaker_drawdown,
            "limit": 100.0,
            "pct_used": drawdown_pct_used,
            "status": _status(drawdown_pct_used),
        },
        {
            "label": "Loss limit",
            "current": rc.circuit_breaker_loss_pct,
            "limit": 100.0,
            "pct_used": rc.circuit_breaker_loss_pct or 0.0,
            "status": _status(rc.circuit_breaker_loss_pct or 0.0),
        },
        {
            "label": "Max order size USD",
            "current": rc.max_order_size_usd,
            "limit": rc.max_order_size_usd,
            "pct_used": 0.0,
            "status": "OK",
        },
    ]

    alert_count = sum(1 for b in bars if b["status"] != "OK")
    return {
        "bars": bars,
        "alert_count": alert_count,
        "trading_allowed": rc.trading_allowed,
        "safe_mode": rc.safe_mode,
        "kill_switch_active": not rc.trading_allowed,
    }
