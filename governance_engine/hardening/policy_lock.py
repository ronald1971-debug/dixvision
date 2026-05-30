"""governance_engine.hardening.policy_lock — Hard policy locking.

Upgrades the advisory PolicyHashAnchor drift detection to a hard enforcement
mode.  When locked:

  * On every check_and_enforce() call, the anchor's verify_no_drift() is run.
  * CLEAN: governance continues normally.
  * DRIFTED: governance decisions are BLOCKED and a CRITICAL hazard is emitted.
    The lock state transitions to LOCKED_DRIFTED.  Execution of new mutations
    is suspended until the operator explicitly unlocks with a reason on record.

Lock/unlock operations are append-only to the authority ledger:
  POLICY_LOCK_ACQUIRED  — operator locked policies
  POLICY_LOCK_RELEASED  — operator unlocked (post-drift investigation)

The lock state persists in a lightweight SQLite row (same pattern as ExposureStore)
so process restarts carry the lock forward.

Authority (L1): stdlib only at module level.
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

_DEFAULT_DB = Path("data") / "policy_lock.db"


class LockStatus(StrEnum):
    UNLOCKED = "UNLOCKED"
    LOCKED_CLEAN = "LOCKED_CLEAN"
    LOCKED_DRIFTED = "LOCKED_DRIFTED"


@dataclass(frozen=True, slots=True)
class PolicyLockState:
    """Snapshot of current policy lock state."""

    status: LockStatus
    locked_by: str          # operator_id or "" when unlocked
    reason: str             # lock/unlock reason
    ts_ns: int


class PolicyLockManager:
    """Hard policy lock — detects drift and enforces execution suspension.

    Args:
        db_path: SQLite path for persistent lock state.
    """

    def __init__(self, *, db_path: Path | str = _DEFAULT_DB) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._state = self._load_state()
        self._check_count: int = 0
        self._drift_count: int = 0

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS policy_lock_state (
                    id        INTEGER PRIMARY KEY CHECK (id = 1),
                    status    TEXT NOT NULL DEFAULT 'UNLOCKED',
                    locked_by TEXT NOT NULL DEFAULT '',
                    reason    TEXT NOT NULL DEFAULT '',
                    ts_ns     INTEGER NOT NULL DEFAULT 0
                )"""
            )
            conn.execute(
                "INSERT OR IGNORE INTO policy_lock_state(id,status,locked_by,reason,ts_ns)"
                " VALUES(1,'UNLOCKED','','',0)"
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path), check_same_thread=False)

    def _load_state(self) -> PolicyLockState:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT status,locked_by,reason,ts_ns FROM policy_lock_state WHERE id=1"
                ).fetchone()
            if row:
                return PolicyLockState(
                    status=LockStatus(row[0]),
                    locked_by=row[1],
                    reason=row[2],
                    ts_ns=row[3],
                )
        except Exception:
            pass
        return PolicyLockState(
            status=LockStatus.UNLOCKED, locked_by="", reason="", ts_ns=0
        )

    def _persist_state(self, state: PolicyLockState) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE policy_lock_state SET status=?,locked_by=?,reason=?,ts_ns=? WHERE id=1",
                    (state.status.value, state.locked_by, state.reason, state.ts_ns),
                )
                conn.commit()
        except Exception as exc:
            _logger.warning("PolicyLockManager: persist error: %s", exc)

    # ------------------------------------------------------------------
    # Operator API
    # ------------------------------------------------------------------

    def lock(self, operator_id: str, ts_ns: int, reason: str = "") -> bool:
        """Operator acquires the policy lock.

        Returns True if lock was newly acquired (False if already locked).
        """
        with self._lock:
            if self._state.status != LockStatus.UNLOCKED:
                return False
            state = PolicyLockState(
                status=LockStatus.LOCKED_CLEAN,
                locked_by=operator_id,
                reason=reason or "operator lock",
                ts_ns=ts_ns,
            )
            self._state = state
            self._persist_state(state)
        self._write_ledger("POLICY_LOCK_ACQUIRED", operator_id, reason, ts_ns)
        _logger.info("PolicyLockManager: locked by %s", operator_id)
        return True

    def unlock(self, operator_id: str, ts_ns: int, reason: str = "") -> bool:
        """Operator releases the policy lock (post-drift investigation).

        Returns True if unlocked, False if already unlocked.
        """
        with self._lock:
            if self._state.status == LockStatus.UNLOCKED:
                return False
            state = PolicyLockState(
                status=LockStatus.UNLOCKED,
                locked_by="",
                reason=reason or f"unlocked by {operator_id}",
                ts_ns=ts_ns,
            )
            self._state = state
            self._persist_state(state)
        self._write_ledger("POLICY_LOCK_RELEASED", operator_id, reason, ts_ns)
        _logger.info("PolicyLockManager: unlocked by %s reason=%s", operator_id, reason)
        return True

    # ------------------------------------------------------------------
    # Enforcement
    # ------------------------------------------------------------------

    def check_and_enforce(self, ts_ns: int) -> PolicyLockState:
        """Run drift check; transition to LOCKED_DRIFTED if drift detected.

        Call on every governance tick.  Returns current PolicyLockState.
        """
        with self._lock:
            self._check_count += 1
            state = self._state

        if state.status == LockStatus.UNLOCKED:
            return state  # not locked — no enforcement

        hazard = self._run_drift_check(ts_ns)
        if hazard is not None:
            # Drift detected while locked → escalate
            with self._lock:
                self._drift_count += 1
                new_state = PolicyLockState(
                    status=LockStatus.LOCKED_DRIFTED,
                    locked_by=self._state.locked_by,
                    reason=f"DRIFT: {getattr(hazard, 'detail', str(hazard))}",
                    ts_ns=ts_ns,
                )
                self._state = new_state
                self._persist_state(new_state)
            self._emit_drift_hazard(ts_ns)
            _logger.critical(
                "PolicyLockManager: DRIFT DETECTED while locked — governance BLOCKED"
            )
            return new_state

        # Still clean
        return self._state

    def governance_blocked(self) -> bool:
        """True when governance decisions should be blocked (LOCKED_DRIFTED)."""
        with self._lock:
            return self._state.status is LockStatus.LOCKED_DRIFTED

    @property
    def current_state(self) -> PolicyLockState:
        with self._lock:
            return self._state

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            s = self._state
        return {
            "status": s.status.value,
            "locked_by": s.locked_by,
            "reason": s.reason,
            "ts_ns": s.ts_ns,
            "check_count": self._check_count,
            "drift_count": self._drift_count,
            "governance_blocked": self.governance_blocked(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _run_drift_check(ts_ns: int) -> Any:
        try:
            from governance_engine.control_plane.policy_hash_anchor import (
                get_policy_hash_anchor,
            )
            anchor = get_policy_hash_anchor()
            if not anchor.is_bound():
                return None
            return anchor.verify_no_drift(ts_ns)
        except Exception as exc:
            _logger.debug("PolicyLockManager: drift check error: %s", exc)
            return None

    @staticmethod
    def _write_ledger(kind: str, operator_id: str, reason: str, ts_ns: int) -> None:
        try:
            from state.ledger.append import append_event
            append_event(
                stream="AUTHORITY",
                kind=kind,
                source="governance_engine",
                payload={
                    "operator_id": operator_id,
                    "reason": reason,
                    "ts_ns": ts_ns,
                },
            )
        except Exception:
            pass

    @staticmethod
    def _emit_drift_hazard(ts_ns: int) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_VIOLATION, {
                "source": "policy_lock",
                "hazard": "POLICY_DRIFT_WHILE_LOCKED",
                "severity": "CRITICAL",
                "ts_ns": ts_ns,
            })
        except Exception:
            pass
        try:
            from state.ledger.append import append_event
            append_event(
                stream="GOVERNANCE",
                kind="POLICY_DRIFT_LOCKED",
                source="governance_engine",
                payload={"ts_ns": ts_ns, "severity": "CRITICAL"},
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: PolicyLockManager | None = None
_manager_lock = threading.Lock()


def get_policy_lock_manager(
    *, db_path: Path | str = _DEFAULT_DB
) -> PolicyLockManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = PolicyLockManager(db_path=db_path)
    return _manager


__all__ = [
    "LockStatus",
    "PolicyLockManager",
    "PolicyLockState",
    "get_policy_lock_manager",
]
