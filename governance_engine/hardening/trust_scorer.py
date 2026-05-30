"""governance_engine.hardening.trust_scorer — Hazard-driven trust erosion.

Extends the minimal TrustEngine with:
  * Hazard-driven erosion: CRITICAL events erode trust by 0.25, WARNING by 0.05
  * SQLite persistence across process restarts
  * ExecutionDisposition: ALLOW (≥0.50), PAPER (0.10–0.50), BLOCK (<0.10)
  * Minimum floor: scores cannot fall below 0.0 or rise above 1.0
  * Passive recovery: +RECOVERY_RATE_PER_TICK on each tick without new hazards
  * all_scores() method for the invariant monitor

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

_DEFAULT_DB = Path("data") / "trust_scores.db"

EROSION_CRITICAL: float = 0.25
EROSION_WARNING: float = 0.05
RECOVERY_RATE_PER_TICK: float = 0.001   # slow passive recovery
DISPOSITION_ALLOW_FLOOR: float = 0.50
DISPOSITION_BLOCK_CEILING: float = 0.10
DEFAULT_INITIAL_SCORE: float = 1.0


class ExecutionDisposition(StrEnum):
    ALLOW = "ALLOW"     # trust ≥ 0.50
    PAPER = "PAPER"     # 0.10 ≤ trust < 0.50 — paper-trade only
    BLOCK = "BLOCK"     # trust < 0.10 — full execution block


@dataclass(frozen=True, slots=True)
class TrustRecord:
    """Snapshot of one engine's trust state."""

    engine_id: str
    score: float
    disposition: ExecutionDisposition
    ts_ns_last_hazard: int
    ts_ns_updated: int


class TrustScorer:
    """Persistent, hazard-driven trust scorer for registered engines.

    Args:
        db_path: SQLite file for score persistence.
        initial_score: starting score for new engines.
    """

    def __init__(
        self,
        *,
        db_path: Path | str = _DEFAULT_DB,
        initial_score: float = DEFAULT_INITIAL_SCORE,
    ) -> None:
        self._db_path = Path(db_path)
        self._initial_score = max(0.0, min(1.0, initial_score))
        self._lock = threading.Lock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._cache: dict[str, float] = self._load_all()
        self._last_hazard_ns: dict[str, int] = {}
        self._tick_count: int = 0

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS trust_scores (
                    engine_id       TEXT PRIMARY KEY,
                    score           REAL NOT NULL DEFAULT 1.0,
                    ts_ns_updated   INTEGER NOT NULL DEFAULT 0
                )"""
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path), check_same_thread=False)

    def _load_all(self) -> dict[str, float]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT engine_id, score FROM trust_scores"
                ).fetchall()
            return {r[0]: float(r[1]) for r in rows}
        except Exception:
            return {}

    def _persist(self, engine_id: str, score: float, ts_ns: int) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO trust_scores(engine_id,score,ts_ns_updated)"
                    " VALUES(?,?,?)",
                    (engine_id, score, ts_ns),
                )
                conn.commit()
        except Exception as exc:
            _logger.warning("TrustScorer: persist error for %s: %s", engine_id, exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(self, engine_id: str) -> float:
        """Return current trust score for *engine_id* (1.0 if unknown)."""
        with self._lock:
            return self._cache.get(engine_id, self._initial_score)

    def disposition(self, engine_id: str) -> ExecutionDisposition:
        """Return execution disposition for *engine_id*."""
        return _score_to_disposition(self.score(engine_id))

    def record(self, engine_id: str, ts_ns: int) -> TrustRecord:
        """Return a full TrustRecord snapshot for *engine_id*."""
        with self._lock:
            s = self._cache.get(engine_id, self._initial_score)
            last_hazard = self._last_hazard_ns.get(engine_id, 0)
        return TrustRecord(
            engine_id=engine_id,
            score=s,
            disposition=_score_to_disposition(s),
            ts_ns_last_hazard=last_hazard,
            ts_ns_updated=ts_ns,
        )

    def erode(self, engine_id: str, severity: str, ts_ns: int) -> float:
        """Apply hazard-driven erosion.

        Args:
            severity: "CRITICAL" → -0.25, "WARNING" → -0.05, else ignored.
        Returns:
            New score after erosion.
        """
        if severity == "CRITICAL":
            delta = -EROSION_CRITICAL
        elif severity == "WARNING":
            delta = -EROSION_WARNING
        else:
            return self.score(engine_id)

        with self._lock:
            current = self._cache.get(engine_id, self._initial_score)
            new_score = max(0.0, current + delta)
            self._cache[engine_id] = new_score
            self._last_hazard_ns[engine_id] = ts_ns

        self._persist(engine_id, new_score, ts_ns)
        _logger.info(
            "TrustScorer: erode %s severity=%s %.3f→%.3f",
            engine_id, severity, current, new_score,
        )
        self._write_ledger(engine_id, current, new_score, severity, ts_ns)
        if new_score < DISPOSITION_BLOCK_CEILING:
            self._emit_critical_trust(engine_id, new_score, ts_ns)
        return new_score

    def recover(self, engine_id: str, ts_ns: int) -> float:
        """Apply one passive recovery tick for *engine_id*.

        Returns new score.
        """
        with self._lock:
            current = self._cache.get(engine_id, self._initial_score)
            if current >= 1.0:
                return current
            new_score = min(1.0, current + RECOVERY_RATE_PER_TICK)
            self._cache[engine_id] = new_score
        self._persist(engine_id, new_score, ts_ns)
        return new_score

    def tick(self, ts_ns: int) -> None:
        """Call once per governance tick to apply passive recovery to all engines."""
        self._tick_count += 1
        if self._tick_count % 10 != 0:
            return  # recover every 10 ticks to reduce DB writes
        with self._lock:
            engine_ids = list(self._cache.keys())
        for eid in engine_ids:
            self.recover(eid, ts_ns)

    def all_scores(self) -> dict[str, float]:
        """Return a snapshot of all known engine scores."""
        with self._lock:
            return dict(self._cache)

    def all_records(self, ts_ns: int) -> list[TrustRecord]:
        """Return TrustRecord for every known engine."""
        with self._lock:
            items = list(self._cache.items())
        return [
            TrustRecord(
                engine_id=eid,
                score=sc,
                disposition=_score_to_disposition(sc),
                ts_ns_last_hazard=self._last_hazard_ns.get(eid, 0),
                ts_ns_updated=ts_ns,
            )
            for eid, sc in items
        ]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            scores = dict(self._cache)
        records = [
            {
                "engine_id": eid,
                "score": round(sc, 4),
                "disposition": _score_to_disposition(sc).value,
            }
            for eid, sc in sorted(scores.items())
        ]
        return {
            "tick_count": self._tick_count,
            "engine_count": len(scores),
            "scores": records,
            "thresholds": {
                "allow": DISPOSITION_ALLOW_FLOOR,
                "block": DISPOSITION_BLOCK_CEILING,
            },
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _write_ledger(
        engine_id: str, old_score: float, new_score: float, severity: str, ts_ns: int
    ) -> None:
        try:
            from state.ledger.append import append_event
            append_event(
                stream="GOVERNANCE",
                kind="TRUST_ERODED",
                source="governance_engine",
                payload={
                    "engine_id": engine_id,
                    "old_score": round(old_score, 4),
                    "new_score": round(new_score, 4),
                    "severity": severity,
                    "ts_ns": ts_ns,
                },
            )
        except Exception:
            pass

    @staticmethod
    def _emit_critical_trust(engine_id: str, score: float, ts_ns: int) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_VIOLATION, {
                "source": "trust_scorer",
                "hazard": "TRUST_BELOW_BLOCK_FLOOR",
                "engine_id": engine_id,
                "score": round(score, 4),
                "severity": "CRITICAL",
                "ts_ns": ts_ns,
            })
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_to_disposition(score: float) -> ExecutionDisposition:
    if score >= DISPOSITION_ALLOW_FLOOR:
        return ExecutionDisposition.ALLOW
    if score >= DISPOSITION_BLOCK_CEILING:
        return ExecutionDisposition.PAPER
    return ExecutionDisposition.BLOCK


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_scorer: TrustScorer | None = None
_scorer_lock = threading.Lock()


def get_trust_scorer(
    *, db_path: Path | str = _DEFAULT_DB, initial_score: float = DEFAULT_INITIAL_SCORE
) -> TrustScorer:
    global _scorer
    with _scorer_lock:
        if _scorer is None:
            _scorer = TrustScorer(db_path=db_path, initial_score=initial_score)
    return _scorer


__all__ = [
    "DEFAULT_INITIAL_SCORE",
    "DISPOSITION_ALLOW_FLOOR",
    "DISPOSITION_BLOCK_CEILING",
    "EROSION_CRITICAL",
    "EROSION_WARNING",
    "ExecutionDisposition",
    "TrustRecord",
    "TrustScorer",
    "get_trust_scorer",
]
