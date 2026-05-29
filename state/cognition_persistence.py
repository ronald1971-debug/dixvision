"""CognitionPersistenceStore — SQLite-backed durability layer for cognitive state.

Stores:
    episodes     — EpisodicMemoryStore / SemanticMemoryStore records
    research_queue  — AutonomousResearchRuntime pending tasks
    research_results — completed research snapshots

Authority: state tier — no engine, no runtime, no execution imports.
INV-15: all ts_ns values are caller-supplied; no internal clock reads.
Thread-safe: WAL mode + single connection per singleton.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from typing import Any

_logger = logging.getLogger(__name__)

_DB_PATH = os.path.join("data", "sqlite", "cognition.db")


class CognitionPersistenceStore:
    """Lightweight SQLite store for cognitive runtime durability.

    Args:
        db_path: Path to the SQLite database file.  Parent directories
            are created automatically on first write.
    """

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.row_factory = sqlite3.Row
            self._conn = conn
        return self._conn

    def _init_db(self) -> None:
        try:
            with self._lock:
                conn = self._connect()
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS episodes (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        store_kind  TEXT    NOT NULL,
                        episode_id  TEXT    NOT NULL,
                        ts_ns       INTEGER NOT NULL,
                        json_blob   TEXT    NOT NULL,
                        created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000000000)
                    );
                    CREATE INDEX IF NOT EXISTS idx_episodes_kind
                        ON episodes(store_kind, ts_ns DESC);

                    CREATE TABLE IF NOT EXISTS research_queue (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic       TEXT    NOT NULL,
                        task_type   TEXT    NOT NULL DEFAULT 'MARKET_ANALYSIS',
                        priority    INTEGER NOT NULL DEFAULT 5,
                        ts_ns       INTEGER NOT NULL,
                        status      TEXT    NOT NULL DEFAULT 'PENDING',
                        created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000000000)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rqueue_status
                        ON research_queue(status, priority, ts_ns);

                    CREATE TABLE IF NOT EXISTS research_results (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic       TEXT    NOT NULL,
                        task_type   TEXT    NOT NULL,
                        status      TEXT    NOT NULL,
                        pages_fetched INTEGER NOT NULL DEFAULT 0,
                        confidence  REAL    NOT NULL DEFAULT 0.0,
                        trust_score REAL    NOT NULL DEFAULT 0.0,
                        sources_json TEXT   NOT NULL DEFAULT '[]',
                        ts_ns       INTEGER NOT NULL,
                        created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000000000)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rresults_ts
                        ON research_results(ts_ns DESC);
                """)
                conn.commit()
        except Exception as exc:
            _logger.warning("CognitionPersistenceStore: init failed: %s", exc)

    # ------------------------------------------------------------------
    # Episode store — EpisodicMemoryStore / SemanticMemoryStore
    # ------------------------------------------------------------------

    def save_episode(
        self,
        *,
        store_kind: str,
        episode_id: str,
        ts_ns: int,
        data: dict[str, Any],
    ) -> None:
        """Persist one episode record (idempotent by episode_id)."""
        try:
            with self._lock:
                conn = self._connect()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO episodes
                        (store_kind, episode_id, ts_ns, json_blob)
                    VALUES (?, ?, ?, ?)
                    """,
                    (store_kind, episode_id, ts_ns, json.dumps(data, default=str)),
                )
                conn.commit()
        except Exception as exc:
            _logger.debug("save_episode error: %s", exc)

    def load_episodes(
        self, store_kind: str, *, limit: int = 500
    ) -> list[dict[str, Any]]:
        """Return up to *limit* most-recent episodes for *store_kind*."""
        try:
            with self._lock:
                conn = self._connect()
                rows = conn.execute(
                    """
                    SELECT episode_id, ts_ns, json_blob
                    FROM episodes
                    WHERE store_kind = ?
                    ORDER BY ts_ns DESC
                    LIMIT ?
                    """,
                    (store_kind, limit),
                ).fetchall()
            return [
                {"episode_id": r["episode_id"], "ts_ns": r["ts_ns"], **json.loads(r["json_blob"])}
                for r in rows
            ]
        except Exception as exc:
            _logger.debug("load_episodes error: %s", exc)
            return []

    def episode_count(self, store_kind: str) -> int:
        try:
            with self._lock:
                conn = self._connect()
                row = conn.execute(
                    "SELECT COUNT(*) FROM episodes WHERE store_kind = ?",
                    (store_kind,),
                ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Research queue
    # ------------------------------------------------------------------

    def enqueue_research(
        self,
        *,
        topic: str,
        task_type: str,
        priority: int,
        ts_ns: int,
    ) -> None:
        """Persist a research task as PENDING."""
        try:
            with self._lock:
                conn = self._connect()
                conn.execute(
                    """
                    INSERT INTO research_queue
                        (topic, task_type, priority, ts_ns, status)
                    VALUES (?, ?, ?, ?, 'PENDING')
                    """,
                    (topic, task_type, priority, ts_ns),
                )
                conn.commit()
        except Exception as exc:
            _logger.debug("enqueue_research error: %s", exc)

    def load_pending_queue(self) -> list[dict[str, Any]]:
        """Return all PENDING research tasks sorted by priority, ts_ns."""
        try:
            with self._lock:
                conn = self._connect()
                rows = conn.execute(
                    """
                    SELECT id, topic, task_type, priority, ts_ns
                    FROM research_queue
                    WHERE status = 'PENDING'
                    ORDER BY priority ASC, ts_ns ASC
                    """,
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            _logger.debug("load_pending_queue error: %s", exc)
            return []

    def mark_queue_done(self, *, topic: str) -> None:
        """Mark the oldest PENDING item for *topic* as DONE."""
        try:
            with self._lock:
                conn = self._connect()
                conn.execute(
                    """
                    UPDATE research_queue
                    SET status = 'DONE'
                    WHERE id = (
                        SELECT id FROM research_queue
                        WHERE topic = ? AND status = 'PENDING'
                        ORDER BY ts_ns ASC
                        LIMIT 1
                    )
                    """,
                    (topic,),
                )
                conn.commit()
        except Exception as exc:
            _logger.debug("mark_queue_done error: %s", exc)

    # ------------------------------------------------------------------
    # Research results
    # ------------------------------------------------------------------

    def save_research_result(
        self,
        *,
        topic: str,
        task_type: str,
        status: str,
        pages_fetched: int,
        confidence: float,
        trust_score: float,
        sources: list[str],
        ts_ns: int,
    ) -> None:
        """Persist a completed research result."""
        try:
            with self._lock:
                conn = self._connect()
                conn.execute(
                    """
                    INSERT INTO research_results
                        (topic, task_type, status, pages_fetched,
                         confidence, trust_score, sources_json, ts_ns)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        topic, task_type, status, pages_fetched,
                        confidence, trust_score, json.dumps(sources), ts_ns,
                    ),
                )
                conn.commit()
        except Exception as exc:
            _logger.debug("save_research_result error: %s", exc)

    def load_recent_results(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return up to *limit* most-recent research results."""
        try:
            with self._lock:
                conn = self._connect()
                rows = conn.execute(
                    """
                    SELECT topic, task_type, status, pages_fetched,
                           confidence, trust_score, sources_json, ts_ns
                    FROM research_results
                    ORDER BY ts_ns DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                try:
                    d["sources"] = json.loads(d.pop("sources_json"))
                except Exception:
                    d["sources"] = []
            return [dict(r) | {"sources": json.loads(r["sources_json"])} for r in rows]
        except Exception as exc:
            _logger.debug("load_recent_results error: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        try:
            with self._lock:
                conn = self._connect()
                ep_count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
                q_pending = conn.execute(
                    "SELECT COUNT(*) FROM research_queue WHERE status='PENDING'"
                ).fetchone()[0]
                q_done = conn.execute(
                    "SELECT COUNT(*) FROM research_queue WHERE status='DONE'"
                ).fetchone()[0]
                r_count = conn.execute("SELECT COUNT(*) FROM research_results").fetchone()[0]
            return {
                "db_path": self._db_path,
                "episodes": ep_count,
                "queue_pending": q_pending,
                "queue_done": q_done,
                "results": r_count,
            }
        except Exception as exc:
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store: CognitionPersistenceStore | None = None
_store_lock = threading.Lock()


def get_cognition_persistence_store(
    db_path: str = _DB_PATH,
) -> CognitionPersistenceStore:
    """Return the process-wide CognitionPersistenceStore singleton."""
    global _store
    with _store_lock:
        if _store is None:
            _store = CognitionPersistenceStore(db_path=db_path)
    return _store


__all__ = [
    "CognitionPersistenceStore",
    "get_cognition_persistence_store",
]
