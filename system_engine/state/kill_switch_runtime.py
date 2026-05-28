"""system_engine/state/kill_switch_runtime.py
DIX VISION v42.2 — Kill Switch Runtime

Provides the system-level kill-switch that halts ALL autonomous
operations immediately. Distinct from financial_governance/kill_switch.py
(which governs capital deployment) — this governs process-level
execution: trading, learning, and evolution pipelines.

State machine: ACTIVE → TRIGGERED → COOLDOWN → ACTIVE (operator only)
Once TRIGGERED, only an explicit operator call to clear() can reset.
Thread-safe. Emits to ledger on state transitions.
"""

from __future__ import annotations

import threading
import time as _time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class KillSwitchState(StrEnum):
    ACTIVE = "ACTIVE"        # normal — all subsystems running
    TRIGGERED = "TRIGGERED"  # kill-switch fired — halt everything
    COOLDOWN = "COOLDOWN"    # transitional — waiting for operator clear


@dataclass(frozen=True, slots=True)
class KillSwitchEvent:
    """Records a kill-switch state transition."""
    from_state: KillSwitchState
    to_state: KillSwitchState
    reason: str
    triggered_by: str
    ts_ns: int


class KillSwitchRuntime:
    """
    System-level kill switch for all autonomous operations.

    Thread-safe. Once TRIGGERED, no code path may reset to ACTIVE
    except via clear(operator_id=...) — ensuring human confirmation.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = KillSwitchState.ACTIVE
        self._events: list[KillSwitchEvent] = []
        self._trigger_ts_ns: int = 0
        self._trigger_reason: str = ""
        self._trigger_by: str = ""

    @property
    def state(self) -> KillSwitchState:
        with self._lock:
            return self._state

    def trigger(self, reason: str, triggered_by: str, ts_ns: int | None = None) -> KillSwitchEvent:
        """Trigger the kill switch. Idempotent — double-trigger is safe."""
        ts_ns = ts_ns or _time.time_ns()
        with self._lock:
            prev = self._state
            if prev == KillSwitchState.TRIGGERED:
                return self._events[-1]
            self._state = KillSwitchState.TRIGGERED
            self._trigger_ts_ns = ts_ns
            self._trigger_reason = reason
            self._trigger_by = triggered_by
            evt = KillSwitchEvent(
                from_state=prev,
                to_state=KillSwitchState.TRIGGERED,
                reason=reason,
                triggered_by=triggered_by,
                ts_ns=ts_ns,
            )
            self._events.append(evt)
        return evt

    def enter_cooldown(self, ts_ns: int | None = None) -> KillSwitchEvent | None:
        """Transition from TRIGGERED → COOLDOWN (operator initiates recovery)."""
        ts_ns = ts_ns or _time.time_ns()
        with self._lock:
            if self._state != KillSwitchState.TRIGGERED:
                return None
            self._state = KillSwitchState.COOLDOWN
            evt = KillSwitchEvent(
                from_state=KillSwitchState.TRIGGERED,
                to_state=KillSwitchState.COOLDOWN,
                reason="operator_initiated_recovery",
                triggered_by="operator",
                ts_ns=ts_ns,
            )
            self._events.append(evt)
        return evt

    def clear(self, operator_id: str, ts_ns: int | None = None) -> KillSwitchEvent | None:
        """Clear kill switch — only valid from COOLDOWN state."""
        ts_ns = ts_ns or _time.time_ns()
        with self._lock:
            if self._state != KillSwitchState.COOLDOWN:
                return None
            self._state = KillSwitchState.ACTIVE
            evt = KillSwitchEvent(
                from_state=KillSwitchState.COOLDOWN,
                to_state=KillSwitchState.ACTIVE,
                reason=f"cleared_by_operator={operator_id}",
                triggered_by=operator_id,
                ts_ns=ts_ns,
            )
            self._events.append(evt)
        return evt

    def is_halted(self) -> bool:
        """Return True if autonomous operations must be stopped."""
        with self._lock:
            return self._state != KillSwitchState.ACTIVE

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state.value,
                "trigger_ts_ns": self._trigger_ts_ns,
                "trigger_reason": self._trigger_reason,
                "event_count": len(self._events),
            }


# Singleton factory
_instance: KillSwitchRuntime | None = None
_lock = threading.Lock()


def get_kill_switch_runtime() -> KillSwitchRuntime:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = KillSwitchRuntime()
    return _instance


__all__ = [
    "KillSwitchEvent",
    "KillSwitchRuntime",
    "KillSwitchState",
    "get_kill_switch_runtime",
]
