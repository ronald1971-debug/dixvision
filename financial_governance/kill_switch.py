"""
financial_governance/kill_switch.py
DIX VISION v42.2 — Financial Kill Switch

The kill switch is the absolute financial emergency halt. When ARMED:
  - All new order placement is blocked unconditionally
  - Open positions are flagged for immediate closure
  - All pending orders are flagged for cancellation
  - The system enters COOLDOWN after the kill switch fires until the
    operator explicitly clears it

KillSwitchState:
  SAFE     — normal operation (no kill switch active)
  ARMED    — kill switch activated; execution blocked
  COOLDOWN — post-kill; execution blocked until operator clears

Triggers:
  - "operator"         — direct operator command (highest trust)
  - "auto_drawdown"    — daily/session drawdown limit exceeded
  - "auto_exposure"    — total exposure exceeds hard cap

The operator always controls the kill switch. Autonomous triggers
arm it but only the operator can clear the COOLDOWN state.
"""

from __future__ import annotations

import threading
import time as _time
from typing import Any

from core.contracts.financial_governance import (
    KillSwitchRecord,
    KillSwitchState,
)
from state.ledger.event_store import append_event


class KillSwitch:
    """
    Financial-layer emergency halt.

    Thread-safe. arm() arms the kill switch; clear() moves from COOLDOWN
    back to SAFE. Only the operator should call clear().
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: KillSwitchState = KillSwitchState.SAFE
        self._last_record: KillSwitchRecord | None = None
        self._arm_count: int = 0

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def arm(
        self,
        reason: str,
        trigger: str,
        positions_closed: int = 0,
        orders_cancelled: int = 0,
    ) -> KillSwitchRecord:
        """
        Arm the kill switch.

        May be called from operator command or autonomous guards.
        Transitions: SAFE → ARMED (then ARMED → COOLDOWN on subsequent arm() call
        or explicitly via enter_cooldown()).
        """
        ts_ns = _time.time_ns()
        with self._lock:
            self._state = KillSwitchState.ARMED
            self._arm_count += 1
            record = KillSwitchRecord(
                ts_ns=ts_ns,
                state=KillSwitchState.ARMED,
                reason=reason,
                trigger=trigger,
                positions_closed=positions_closed,
                orders_cancelled=orders_cancelled,
            )
            self._last_record = record

        append_event(
            "GOVERNANCE",
            "FINGOV_KILL_SWITCH_ARMED",
            "financial_governance.kill_switch",
            {
                "reason": reason,
                "trigger": trigger,
                "positions_closed": positions_closed,
                "orders_cancelled": orders_cancelled,
            },
        )

        return record

    def enter_cooldown(self, reason: str = "post-kill cooldown") -> KillSwitchRecord:
        """
        Transition from ARMED to COOLDOWN.

        Called after positions are closed and orders are cancelled.
        Execution remains blocked in COOLDOWN.
        """
        ts_ns = _time.time_ns()
        with self._lock:
            self._state = KillSwitchState.COOLDOWN
            record = KillSwitchRecord(
                ts_ns=ts_ns,
                state=KillSwitchState.COOLDOWN,
                reason=reason,
                trigger="internal",
            )
            self._last_record = record

        append_event(
            "GOVERNANCE",
            "FINGOV_KILL_SWITCH_COOLDOWN",
            "financial_governance.kill_switch",
            {"reason": reason},
        )

        return record

    def clear(self, operator_id: str = "operator") -> KillSwitchRecord:
        """
        Clear the kill switch and return to SAFE state.

        Only the operator may call this. The guard does not enforce caller
        identity here — that is enforced by OperatorConstitution.
        """
        ts_ns = _time.time_ns()
        with self._lock:
            prev_state = self._state
            self._state = KillSwitchState.SAFE
            record = KillSwitchRecord(
                ts_ns=ts_ns,
                state=KillSwitchState.SAFE,
                reason=f"cleared by {operator_id}",
                trigger="operator",
            )
            self._last_record = record

        append_event(
            "GOVERNANCE",
            "FINGOV_KILL_SWITCH_CLEARED",
            "financial_governance.kill_switch",
            {
                "previous_state": prev_state.value,
                "operator_id": operator_id,
            },
        )

        return record

    # ------------------------------------------------------------------
    # Gate
    # ------------------------------------------------------------------

    def is_active(self) -> bool:
        """Return True if the kill switch is ARMED or in COOLDOWN."""
        with self._lock:
            return self._state is not KillSwitchState.SAFE

    def state(self) -> KillSwitchState:
        with self._lock:
            return self._state

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def arm_count(self) -> int:
        with self._lock:
            return self._arm_count

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state.value,
                "arm_count": self._arm_count,
                "last_reason": self._last_record.reason if self._last_record else None,
                "last_trigger": (
                    self._last_record.trigger if self._last_record else None
                ),
            }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: KillSwitch | None = None
_lock = threading.Lock()


def get_kill_switch() -> KillSwitch:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = KillSwitch()
    return _instance


__all__ = ["KillSwitch", "get_kill_switch"]
