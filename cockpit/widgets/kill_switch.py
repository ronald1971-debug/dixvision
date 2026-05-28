"""Cockpit widget — kill switch control."""

from __future__ import annotations

from typing import Any

from system.fast_risk_cache import get_risk_cache

__all__ = ["kill_switch_state", "activate_kill_switch", "deactivate_kill_switch"]


def kill_switch_state() -> dict[str, Any]:
    rc = get_risk_cache().get()
    return {
        "active": not rc.trading_allowed,
        "safe_mode": rc.safe_mode,
        "trading_allowed": rc.trading_allowed,
        "risk_version": rc.version_id,
    }


def activate_kill_switch(operator_id: str, reason: str) -> dict[str, Any]:
    get_risk_cache().halt_trading(reason=reason)
    return {"accepted": True, "reason": reason}


def deactivate_kill_switch(operator_id: str) -> dict[str, Any]:
    get_risk_cache().resume_trading()
    return {"accepted": True}
