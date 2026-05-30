"""evolution_engine.lifecycle.audit — Stage 8: deterministic replay audit trail.

ReplayAuditTrail persists every per-stage decision for each proposal in
SQLite so that any proposal can be fully replayed and inspected
post-deployment.  Uses WAL mode for concurrent read safety.

Schema:
  audit_log(id, proposal_id, stage, note, operator_id, ts_ns)

replay_proposal() returns the ordered event stream for one proposal,
enabling deterministic reconstruction of why a mutation was accepted or
rejected at each gate.

Authority (L2/B1): stdlib only at module level.
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from evolution_engine.lifecycle.contracts import ProposalRecord

_logger = logging.getLogger(__name__)

_DEFAULT_DB = Path("data") / "evolution_audit.db"


class ReplayAuditTrail:
    """SQLite-backed per-stage decision log for every lifecycle proposal.

    Args:
        db_path: path to the SQLite database file.
    """

    def __init__(self, *, db_path: Path | str = _DEFAULT_DB) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._write_count: int = 0
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id TEXT    NOT NULL,
                    stage       TEXT    NOT NULL,
                    note        TEXT    NOT NULL,
                    operator_id TEXT    NOT NULL,
                    ts_ns       INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_proposal "
                "ON audit_log(proposal_id, ts_ns)"
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path), check_same_thread=False)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record_decision(
        self,
        proposal_id: str,
        stage: str,
        note: str,
        operator_id: str,
        ts_ns: int,
    ) -> None:
        """Persist one stage decision.  Never raises."""
        try:
            with self._lock:
                with self._connect() as conn:
                    conn.execute(
                        "INSERT INTO audit_log(proposal_id, stage, note, operator_id, ts_ns) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (proposal_id, stage, note, operator_id, ts_ns),
                    )
                    conn.commit()
                    self._write_count += 1
        except Exception as exc:
            _logger.debug("ReplayAuditTrail.record_decision error: %s", exc)

    def record_proposal(self, record: "ProposalRecord") -> None:
        """Flush the in-memory audit_trail from *record* into SQLite."""
        for entry in record.audit_trail:
            self.record_decision(
                proposal_id=record.proposal_id,
                stage=entry.stage,
                note=entry.note,
                operator_id=entry.operator_id,
                ts_ns=entry.ts_ns,
            )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_trail(self, proposal_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Return the ordered audit trail for one proposal (oldest first)."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT stage, note, operator_id, ts_ns "
                    "FROM audit_log WHERE proposal_id = ? "
                    "ORDER BY ts_ns ASC LIMIT ?",
                    (proposal_id, limit),
                ).fetchall()
            return [
                {"stage": r[0], "note": r[1], "operator_id": r[2], "ts_ns": r[3]}
                for r in rows
            ]
        except Exception as exc:
            _logger.debug("ReplayAuditTrail.get_trail error: %s", exc)
            return []

    def replay_proposal(self, proposal_id: str) -> dict[str, Any]:
        """Return a complete replay document for *proposal_id*."""
        trail = self.get_trail(proposal_id, limit=500)
        return {
            "proposal_id": proposal_id,
            "entry_count": len(trail),
            "trail": trail,
        }

    def recent_proposals(self, limit: int = 20) -> list[str]:
        """Return distinct proposal_ids from most recent decisions."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT DISTINCT proposal_id FROM audit_log "
                    "ORDER BY ts_ns DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [r[0] for r in rows]
        except Exception as exc:
            _logger.debug("ReplayAuditTrail.recent_proposals error: %s", exc)
            return []

    @property
    def write_count(self) -> int:
        return self._write_count


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_trail: ReplayAuditTrail | None = None
_trail_lock = threading.Lock()


def get_replay_audit_trail(
    *, db_path: Path | str = _DEFAULT_DB
) -> ReplayAuditTrail:
    """Return the process-wide ReplayAuditTrail singleton."""
    global _trail
    with _trail_lock:
        if _trail is None:
            _trail = ReplayAuditTrail(db_path=db_path)
    return _trail


__all__ = ["ReplayAuditTrail", "get_replay_audit_trail"]
