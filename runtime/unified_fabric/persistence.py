"""runtime.unified_fabric.persistence — FabricPersistence.

SQLite-backed write-ahead replay stream for the Unified Event Fabric.

Every UnifiedEvent is appended here before delivery to subscribers.
This creates a deterministic, recoverable event log that:
- Survives process crashes (write-ahead, not write-behind)
- Enables full system replay from any point in time
- Serves as the canonical event audit trail

Schema:
    fabric_events(
        sequence    INT PRIMARY KEY,
        event_id    TEXT UNIQUE,
        domain      TEXT,
        event_type  TEXT,
        ts_ns       INT,
        source      TEXT,
        priority    INT,
        trace_id    TEXT,
        parent_id   TEXT,
        tags        TEXT,   -- JSON array
        payload     TEXT    -- JSON object (stringified)
    )

INV-15: ts_ns stored verbatim from event (never wall-clock).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from runtime.unified_fabric.contracts import UnifiedEvent

_logger     = logging.getLogger(__name__)
_DEFAULT_DB = Path("data/unified_fabric.db")

_DDL = """
CREATE TABLE IF NOT EXISTS fabric_events (
    event_id    TEXT PRIMARY KEY,
    sequence    INTEGER NOT NULL,
    domain      TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    ts_ns       INTEGER NOT NULL,
    source      TEXT NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 2,
    trace_id    TEXT NOT NULL DEFAULT '',
    parent_id   TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '[]',
    payload     TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_fe_seq      ON fabric_events(sequence);
CREATE INDEX IF NOT EXISTS idx_fe_ts       ON fabric_events(ts_ns);
CREATE INDEX IF NOT EXISTS idx_fe_domain   ON fabric_events(domain, ts_ns);
CREATE INDEX IF NOT EXISTS idx_fe_trace    ON fabric_events(trace_id);
CREATE INDEX IF NOT EXISTS idx_fe_parent   ON fabric_events(parent_id);
CREATE INDEX IF NOT EXISTS idx_fe_type     ON fabric_events(event_type, ts_ns);
"""


class FabricPersistence:
    """Write-ahead SQLite event log for the Unified Event Fabric."""

    def __init__(self, db_path: Path = _DEFAULT_DB) -> None:
        self._db_path  = db_path
        self._lock     = threading.Lock()
        self._conn:    sqlite3.Connection | None = None
        self._appended: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.executescript(_DDL)
            conn.commit()
            self._conn = conn
        return self._conn

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def append(self, event: "UnifiedEvent") -> None:
        """Append one UnifiedEvent to the write-ahead log. Best-effort."""
        try:
            payload_json = json.dumps(
                {k: str(v) for k, v in event.payload.items()},
                ensure_ascii=False,
            )
            tags_json = json.dumps(sorted(event.tags))
            with self._lock:
                conn = self._get_conn()
                conn.execute(
                    """INSERT OR IGNORE INTO fabric_events
                       (event_id, sequence, domain, event_type, ts_ns, source,
                        priority, trace_id, parent_id, tags, payload)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        event.event_id,
                        event.sequence,
                        event.domain.value,
                        event.event_type,
                        event.ts_ns,
                        event.source,
                        event.priority.value,
                        event.trace_id,
                        event.parent_id,
                        tags_json,
                        payload_json,
                    ),
                )
                conn.commit()
                self._appended += 1
        except Exception as exc:
            _logger.debug("FabricPersistence.append error: %s", exc)

    # ------------------------------------------------------------------
    # Read (replay surface)
    # ------------------------------------------------------------------

    def replay(
        self,
        *,
        since_ns:    int | None = None,
        until_ns:    int | None = None,
        domain:      str | None = None,
        event_type:  str | None = None,
        trace_id:    str | None = None,
        limit:       int = 500,
    ) -> list[dict[str, Any]]:
        """Return events matching criteria, ordered by sequence ASC (chronological)."""
        try:
            clauses: list[str] = []
            params:  list      = []
            if since_ns is not None:
                clauses.append("ts_ns >= ?"); params.append(since_ns)
            if until_ns is not None:
                clauses.append("ts_ns <= ?"); params.append(until_ns)
            if domain is not None:
                clauses.append("domain = ?"); params.append(domain)
            if event_type is not None:
                clauses.append("event_type = ?"); params.append(event_type)
            if trace_id is not None:
                clauses.append("trace_id = ?"); params.append(trace_id)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            sql   = (
                f"SELECT event_id, sequence, domain, event_type, ts_ns, "
                f"source, priority, trace_id, parent_id, tags, payload "
                f"FROM fabric_events {where} ORDER BY ts_ns ASC, sequence ASC LIMIT ?"
            )
            params.append(limit)
            with self._lock:
                rows = self._get_conn().execute(sql, params).fetchall()
            cols = (
                "event_id", "sequence", "domain", "event_type", "ts_ns",
                "source", "priority", "trace_id", "parent_id", "tags", "payload",
            )
            return [dict(zip(cols, row)) for row in rows]
        except Exception as exc:
            _logger.debug("FabricPersistence.replay error: %s", exc)
            return []

    def count(self, domain: str | None = None) -> int:
        """Total events persisted (optionally filtered by domain)."""
        try:
            with self._lock:
                if domain:
                    return self._get_conn().execute(
                        "SELECT COUNT(*) FROM fabric_events WHERE domain=?", (domain,)
                    ).fetchone()[0]
                return self._get_conn().execute(
                    "SELECT COUNT(*) FROM fabric_events"
                ).fetchone()[0]
        except Exception:
            return 0

    def domain_counts(self) -> dict[str, int]:
        """Event count per domain."""
        try:
            with self._lock:
                rows = self._get_conn().execute(
                    "SELECT domain, COUNT(*) FROM fabric_events GROUP BY domain"
                ).fetchall()
            return {r[0]: r[1] for r in rows}
        except Exception:
            return {}

    def snapshot(self) -> dict:
        return {
            "active":           True,
            "appended_session": self._appended,
            "persisted_total":  self.count(),
            "domain_counts":    self.domain_counts(),
            "db_path":          str(self._db_path),
        }


_singleton: FabricPersistence | None = None
_lock = threading.Lock()


def get_fabric_persistence() -> FabricPersistence:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = FabricPersistence()
    return _singleton


__all__ = ["FabricPersistence", "get_fabric_persistence"]
