"""
operator_governance/manual_lockout.py
DIX VISION v42.2 — Manual Lockout Guard

The operator may halt any scope of the system at any time without
requiring justification. Lockouts are an absolute override — no
autonomous process may lift a manual lockout.

Scopes (LockoutScope):
  ALL             — halt everything
  EXECUTION       — halt execution path only
  LEARNING        — halt learning/evolution only
  AUTONOMOUS_OPS  — halt autonomous ops only

Invariants:
  - A lockout may only be lifted by the operator explicitly.
  - Multiple concurrent lockouts at different scopes are supported.
  - Lockout state is always recorded in the governance ledger.
  - is_locked(scope) is safe to call from any thread at any time.
"""

from __future__ import annotations

import threading
import time as _time
import uuid
from typing import Any

from core.contracts.operator_governance import (
    LockoutRecord,
    LockoutScope,
)
from state.ledger.event_store import append_event


class ManualLockoutGuard:
    """
    Registry and gate for manual operator lockouts.

    Thread-safe. Callers use is_locked(scope) to gate execution.
    The operator uses issue_lockout() and lift_lockout().
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # lockout_id → LockoutRecord
        self._active: dict[str, LockoutRecord] = {}
        # Resolved history
        self._history: list[LockoutRecord] = []
        self._total_issued: int = 0
        self._total_lifted: int = 0

    # ------------------------------------------------------------------
    # Lockout lifecycle
    # ------------------------------------------------------------------

    def issue_lockout(
        self,
        scope: LockoutScope,
        reason: str,
        issued_by: str = "operator",
    ) -> LockoutRecord:
        """
        Issue a manual lockout. Returns the active LockoutRecord.

        Emits OPGOV_LOCKOUT_ISSUED to the governance ledger.
        """
        lockout_id = str(uuid.uuid4())
        ts_ns = _time.time_ns()

        record = LockoutRecord(
            lockout_id=lockout_id,
            ts_ns=ts_ns,
            scope=scope,
            reason=reason,
            active=True,
            issued_by=issued_by,
            lifted_ts_ns=0,
        )

        with self._lock:
            self._active[lockout_id] = record
            self._total_issued += 1

        append_event(
            "GOVERNANCE",
            "OPGOV_LOCKOUT_ISSUED",
            "operator_governance.manual_lockout",
            {
                "lockout_id": lockout_id,
                "scope": scope.value,
                "reason": reason,
                "issued_by": issued_by,
            },
        )

        return record

    def lift_lockout(
        self,
        lockout_id: str,
        lifted_by: str = "operator",
    ) -> bool:
        """
        Lift a lockout. Returns True if found and lifted.

        Only the operator should call this. The guard does not enforce
        caller identity here — that is enforced by OperatorConstitution.
        """
        ts_ns = _time.time_ns()
        with self._lock:
            record = self._active.pop(lockout_id, None)
            if record is None:
                return False
            lifted = LockoutRecord(
                lockout_id=record.lockout_id,
                ts_ns=record.ts_ns,
                scope=record.scope,
                reason=record.reason,
                active=False,
                issued_by=record.issued_by,
                lifted_ts_ns=ts_ns,
            )
            self._history.append(lifted)
            self._total_lifted += 1

        append_event(
            "GOVERNANCE",
            "OPGOV_LOCKOUT_LIFTED",
            "operator_governance.manual_lockout",
            {
                "lockout_id": lockout_id,
                "scope": lifted.scope.value,
                "lifted_by": lifted_by,
                "duration_ns": ts_ns - lifted.ts_ns,
            },
        )

        return True

    # ------------------------------------------------------------------
    # Gate
    # ------------------------------------------------------------------

    def is_locked(self, scope: LockoutScope) -> bool:
        """
        Return True if any active lockout covers the given scope.

        ALL lockout always matches every scope query.
        """
        with self._lock:
            for record in self._active.values():
                if record.scope is LockoutScope.ALL:
                    return True
                if record.scope is scope:
                    return True
        return False

    def active_lockouts(self) -> list[LockoutRecord]:
        with self._lock:
            return list(self._active.values())

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def is_any_locked(self) -> bool:
        with self._lock:
            return bool(self._active)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active_lockouts": len(self._active),
                "total_issued": self._total_issued,
                "total_lifted": self._total_lifted,
                "scopes_locked": [r.scope.value for r in self._active.values()],
            }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: ManualLockoutGuard | None = None
_lock = threading.Lock()


def get_manual_lockout_guard() -> ManualLockoutGuard:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ManualLockoutGuard()
    return _instance


__all__ = ["ManualLockoutGuard", "get_manual_lockout_guard"]
