"""Cockpit API — /risk payload builder.

Wraps get_risk_cache() for the cockpit operator surface.
Called by ui/cockpit_routes.py.
"""

from __future__ import annotations

from typing import Any

from system.fast_risk_cache import get_risk_cache

__all__ = ["risk_payload"]


def risk_payload() -> dict[str, Any]:
    rc = get_risk_cache().get()
    return {
        "max_order_size_usd": rc.max_order_size_usd,
        "max_position_pct": rc.max_position_pct,
        "circuit_breaker_drawdown": rc.circuit_breaker_drawdown,
        "circuit_breaker_loss_pct": rc.circuit_breaker_loss_pct,
        "trading_allowed": rc.trading_allowed,
        "safe_mode": rc.safe_mode,
        "last_updated_utc": rc.last_updated_utc,
        "version_id": rc.version_id,
        "version": rc.version,
    }
