"""state.memory.timeline — CognitionTimeline.

Append-only SQLite-backed log of every MemoryRecord written to the
Unified Cognitive Memory Layer. Provides chronological query and
replay-by-time-range.

Schema:
    memory_timeline(record_id TEXT PK, kind TEXT, ts_ns INT,
                    source TEXT, summary TEXT, body TEXT,
                    tags TEXT, confidence REAL, parent_id TEXT)

INV-15: ts_ns is always caller-supplied; no wall-clock inside this module.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state.memory.contracts import MemoryKind, MemoryRecord

_logger = logging.getLogger(__name__)
_DEFAULT_DB = Path("data/memory_timeline.db")

_DDL = """
CREATE TABLE IF NOT EXISTS memory_timeline (
    record_id  TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,
    ts_ns      INTEGER NOT NULL,
    source     TEXT NOT NULL,
    summary    TEXT NOT NULL,
    body       TEXT NOT NULL DEFAULT '{}',
    tags       TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT -1.0,
    parent_id  TEXT
);
CREATE INDEX IF NOT EXISTS idx_timeline_ts    ON memory_timeline(ts_ns);
CREATE INDEX IF NOT EXISTS idx_timeline_kind  ON memory_timeline(kind, ts_ns);
CREATE INDEX IF NOT EXISTS idx_timeline_src   ON memory_timeline(source, ts_ns);
"""


class CognitionTimeline:
    """Append-only ordered log of all cognitive memory records."""

    def __init__(self, db_path: Path = _DEFAULT_DB) -> None:
        self._db_path = db_path
        self._lock    = threading.Lock()
        self._conn:   sqlite3.Connection | None = None
        self._total:  int = 0

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

    def append(self, record: "MemoryRecord") -> None:
        """Append one record to the timeline. Best-effort; never raises."""
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute(
                    """INSERT OR IGNORE INTO memory_timeline
                       (record_id, kind, ts_ns, source, summary,
                        body, tags, confidence, parent_id)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        record.record_id,
                        record.kind.value,
                        record.ts_ns,
                        record.source,
                        record.summary,
                        json.dumps(dict(record.body)),
                        json.dumps(sorted(record.tags)),
                        record.confidence,
                        record.parent_id,
                    ),
                )
                conn.commit()
                self._total += 1
        except Exception as exc:
            _logger.debug("timeline.append error: %s", exc)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query(
        self,
        *,
        since_ns:  int | None = None,
        until_ns:  int | None = None,
        kinds:     list[str] | None = None,
        source:    str | None = None,
        limit:     int = 50,
    ) -> list[dict]:
        """Return matching rows as plain dicts, newest-first."""
        try:
            clauses: list[str] = []
            params:  list      = []
            if since_ns is not None:
                clauses.append("ts_ns >= ?"); params.append(since_ns)
            if until_ns is not None:
                clauses.append("ts_ns <= ?"); params.append(until_ns)
            if kinds:
                placeholders = ",".join("?" * len(kinds))
                clauses.append(f"kind IN ({placeholders})")
                params.extend(kinds)
            if source is not None:
                clauses.append("source = ?"); params.append(source)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            sql   = f"SELECT * FROM memory_timeline {where} ORDER BY ts_ns DESC LIMIT ?"
            params.append(limit)
            with self._lock:
                conn = self._get_conn()
                rows = conn.execute(sql, params).fetchall()
            cols = ("record_id", "kind", "ts_ns", "source", "summary",
                    "body", "tags", "confidence", "parent_id")
            return [dict(zip(cols, row)) for row in rows]
        except Exception as exc:
            _logger.debug("timeline.query error: %s", exc)
            return []

    def count(self) -> int:
        try:
            with self._lock:
                return self._get_conn().execute(
                    "SELECT COUNT(*) FROM memory_timeline"
                ).fetchone()[0]
        except Exception:
            return 0

    def snapshot(self) -> dict:
        return {
            "active":    True,
            "total_appended": self._total,
            "persisted": self.count(),
            "db_path":   str(self._db_path),
        }


_singleton: CognitionTimeline | None = None
_lock = threading.Lock()


def get_cognition_timeline() -> CognitionTimeline:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = CognitionTimeline()
    return _singleton


__all__ = ["CognitionTimeline", "get_cognition_timeline"]
