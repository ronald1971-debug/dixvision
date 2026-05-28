"""Cockpit API — /autonomy payload builder + mode setter."""

from __future__ import annotations

from typing import Any

from system.autonomy import AutonomyMode, get_autonomy

__all__ = ["autonomy_payload", "set_autonomy_mode"]


def autonomy_payload() -> dict[str, Any]:
    s = get_autonomy().status()  # returns AutonomyStatus
    return {
        "mode": s.mode.value,
        "budget": {
            "max_size_usd": s.budget.max_size_usd,
            "max_trades_per_hour": s.budget.max_trades_per_hour,
            "auto_asset_allowed": s.budget.auto_asset_allowed,
        },
        "trades_last_hour": s.trades_last_hour,
        "last_changed_utc": s.last_changed_utc,
    }


def set_autonomy_mode(mode_str: str, operator_id: str, reason: str = "") -> dict[str, Any]:
    try:
        mode = AutonomyMode(mode_str.upper())
    except ValueError:
        valid = [m.value for m in AutonomyMode]
        return {"accepted": False, "reason": f"Unknown mode {mode_str!r}. Valid: {valid}"}
    result = get_autonomy().transition(mode, operator_id=operator_id, reason=reason)
    return {"accepted": True, "mode": result.mode.value}
