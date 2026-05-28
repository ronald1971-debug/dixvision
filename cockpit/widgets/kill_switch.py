"""Cockpit widget — kill switch control.

Provides a UI data model for the kill switch widget.
Does NOT construct bus events (B27/B28). B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["KillSwitchState", "KillSwitchWidget"]


@dataclass(frozen=True, slots=True)
class KillSwitchState:
    active: bool
    activated_at_ns: int
    activated_by: str
    reason: str
    safe_mode_available: bool


class KillSwitchWidget:
    """Read/write interface for the kill switch UI panel."""

    def __init__(self, kill_switch: Any, operator_handler: Any) -> None:
        self._ks = kill_switch
        self._handler = operator_handler

    def get_state(self, ts_ns: int) -> KillSwitchState:
        state = self._ks.current_state()
        return KillSwitchState(
            active=state.active,
            activated_at_ns=state.activated_at_ns,
            activated_by=state.activated_by,
            reason=state.reason,
            safe_mode_available=not state.active,
        )

    def activate(self, ts_ns: int, operator_id: str, reason: str) -> dict[str, Any]:
        result = self._ks.activate(reason=reason, activated_by=operator_id, ts_ns=ts_ns)
        return {"accepted": result.accepted, "reason": result.reason}

    def deactivate(self, ts_ns: int, operator_id: str) -> dict[str, Any]:
        result = self._ks.deactivate(deactivated_by=operator_id, ts_ns=ts_ns)
        return {"accepted": result.accepted, "reason": getattr(result, "reason", "")}
