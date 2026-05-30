"""governance_engine.hardening.execution_auditor — Execution decision audit log.

Every execution decision (fill, reject, gate block) is recorded to a
SQLite-backed audit log.  The auditor also runs lightweight anomaly
detection:

  FREQ-ANOMALY  — per-symbol fill frequency exceeds FILL_FREQ_MAX_PER_MIN
  SIZE-ANOMALY  — single notional value exceeds NOTIONAL_ANOMALY_USD
  BURST-ANOMALY — rolling 60-second fill burst exceeds BURST_MAX_FILLS

Anomalies are emitted as DYON_VIOLATION events and appended to the
GOVERNANCE ledger stream.

Authority (L1): stdlib only at module level.
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

_DEFAULT_DB = Path("data") / "execution_audit.db"

FILL_FREQ_MAX_PER_MIN: int = 120        # fills per symbol per minute
NOTIONAL_ANOMALY_USD: float = 500_000.0 # single fill notional threshold
BURST_MAX_FILLS: int = 50               # total fills in any 60-second window

_NS_PER_MIN: int = 60_000_000_000


class AuditOutcome(StrEnum):
    FILLED   = "FILLED"
    REJECTED = "REJECTED"
    BLOCKED  = "BLOCKED"   # gate blocked
    PARTIAL  = "PARTIAL"


@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    """Immutable record of one execution decision."""

    decision_id: str
    symbol: str
    side: str           # BUY | SELL
    quantity: float
    price: float
    notional_usd: float
    outcome: AuditOutcome
    source_engine: str
    venue: str
    reason: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class AnomalyReport:
    """Detected execution anomaly."""

    kind: str
    symbol: str
    detail: str
    ts_ns: int


class ExecutionAuditor:
    """SQLite-backed execution decision auditor with anomaly detection.

    Args:
        db_path: SQLite file path.
        row_limit: maximum rows to return in queries (default 500).
    """

    def __init__(
        self,
        *,
        db_path: Path | str = _DEFAULT_DB,
        row_limit: int = 500,
    ) -> None:
        self._db_path = Path(db_path)
        self._row_limit = row_limit
        self._lock = threading.Lock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        # In-memory rolling windows for anomaly detection
        # {symbol: deque[(ts_ns,)]}
        self._symbol_fills: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=FILL_FREQ_MAX_PER_MIN * 2)
        )
        # Global burst window: deque[ts_ns]
        self._burst_window: deque = deque(maxlen=BURST_MAX_FILLS * 2)

        self._decision_count: int = 0
        self._anomaly_count: int = 0

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS execution_decisions (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_id   TEXT NOT NULL,
                    symbol        TEXT NOT NULL,
                    side          TEXT NOT NULL,
                    quantity      REAL NOT NULL,
                    price         REAL NOT NULL,
                    notional_usd  REAL NOT NULL,
                    outcome       TEXT NOT NULL,
                    source_engine TEXT NOT NULL,
                    venue         TEXT NOT NULL,
                    reason        TEXT NOT NULL,
                    ts_ns         INTEGER NOT NULL
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_exec_symbol_ts "
                "ON execution_decisions(symbol, ts_ns)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_exec_ts "
                "ON execution_decisions(ts_ns)"
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path), check_same_thread=False)

    # ------------------------------------------------------------------
    # Record
    # ------------------------------------------------------------------

    def record(self, decision: ExecutionDecision) -> list[AnomalyReport]:
        """Record an execution decision and run anomaly checks.

        Returns a (possibly empty) list of detected anomalies.
        """
        self._persist(decision)
        with self._lock:
            self._decision_count += 1

        anomalies = self._detect_anomalies(decision)
        if anomalies:
            with self._lock:
                self._anomaly_count += len(anomalies)
            for a in anomalies:
                self._emit_anomaly(a)
        return anomalies

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent *limit* decisions (newest first)."""
        limit = min(limit, self._row_limit)
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT decision_id,symbol,side,quantity,price,notional_usd,"
                    "outcome,source_engine,venue,reason,ts_ns "
                    "FROM execution_decisions ORDER BY ts_ns DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [_row_to_dict(r) for r in rows]
        except Exception as exc:
            _logger.debug("ExecutionAuditor.recent error: %s", exc)
            return []

    def by_symbol(self, symbol: str, limit: int = 50) -> list[dict[str, Any]]:
        limit = min(limit, self._row_limit)
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT decision_id,symbol,side,quantity,price,notional_usd,"
                    "outcome,source_engine,venue,reason,ts_ns "
                    "FROM execution_decisions WHERE symbol=? "
                    "ORDER BY ts_ns DESC LIMIT ?",
                    (symbol, limit),
                ).fetchall()
            return [_row_to_dict(r) for r in rows]
        except Exception as exc:
            _logger.debug("ExecutionAuditor.by_symbol error: %s", exc)
            return []

    def symbol_stats(self) -> list[dict[str, Any]]:
        """Aggregate fill stats per symbol."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT symbol, COUNT(*) as fills, SUM(notional_usd) as total_notional,"
                    " AVG(price) as avg_price, MAX(ts_ns) as last_ts "
                    "FROM execution_decisions WHERE outcome='FILLED' "
                    "GROUP BY symbol ORDER BY fills DESC LIMIT 100"
                ).fetchall()
            return [
                {
                    "symbol": r[0],
                    "fills": r[1],
                    "total_notional_usd": round(r[2] or 0.0, 2),
                    "avg_price": round(r[3] or 0.0, 6),
                    "last_ts_ns": r[4],
                }
                for r in rows
            ]
        except Exception as exc:
            _logger.debug("ExecutionAuditor.symbol_stats error: %s", exc)
            return []

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            decisions = self._decision_count
            anomalies = self._anomaly_count
        return {
            "decision_count": decisions,
            "anomaly_count": anomalies,
            "thresholds": {
                "fill_freq_max_per_min": FILL_FREQ_MAX_PER_MIN,
                "notional_anomaly_usd": NOTIONAL_ANOMALY_USD,
                "burst_max_fills": BURST_MAX_FILLS,
            },
        }

    # ------------------------------------------------------------------
    # Anomaly detection
    # ------------------------------------------------------------------

    def _detect_anomalies(self, decision: ExecutionDecision) -> list[AnomalyReport]:
        if decision.outcome not in (AuditOutcome.FILLED, AuditOutcome.PARTIAL):
            return []

        anomalies: list[AnomalyReport] = []
        ts = decision.ts_ns
        symbol = decision.symbol
        window_start = ts - _NS_PER_MIN

        with self._lock:
            # Update rolling windows
            self._symbol_fills[symbol].append(ts)
            self._burst_window.append(ts)

            # FREQ-ANOMALY: per-symbol fills in last minute
            recent_sym = [t for t in self._symbol_fills[symbol] if t >= window_start]
            if len(recent_sym) > FILL_FREQ_MAX_PER_MIN:
                anomalies.append(AnomalyReport(
                    kind="FREQ-ANOMALY",
                    symbol=symbol,
                    detail=(
                        f"{len(recent_sym)} fills/{symbol} in last 60s "
                        f"exceeds limit={FILL_FREQ_MAX_PER_MIN}"
                    ),
                    ts_ns=ts,
                ))

            # BURST-ANOMALY: total fills across all symbols in last minute
            recent_burst = [t for t in self._burst_window if t >= window_start]
            if len(recent_burst) > BURST_MAX_FILLS:
                anomalies.append(AnomalyReport(
                    kind="BURST-ANOMALY",
                    symbol=symbol,
                    detail=(
                        f"{len(recent_burst)} total fills in last 60s "
                        f"exceeds burst limit={BURST_MAX_FILLS}"
                    ),
                    ts_ns=ts,
                ))

        # SIZE-ANOMALY: check notional (no lock needed — immutable decision)
        if decision.notional_usd > NOTIONAL_ANOMALY_USD:
            anomalies.append(AnomalyReport(
                kind="SIZE-ANOMALY",
                symbol=symbol,
                detail=(
                    f"notional_usd={decision.notional_usd:,.0f} "
                    f"exceeds threshold={NOTIONAL_ANOMALY_USD:,.0f}"
                ),
                ts_ns=ts,
            ))

        return anomalies

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _persist(self, decision: ExecutionDecision) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO execution_decisions"
                    "(decision_id,symbol,side,quantity,price,notional_usd,"
                    "outcome,source_engine,venue,reason,ts_ns)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        decision.decision_id, decision.symbol, decision.side,
                        decision.quantity, decision.price, decision.notional_usd,
                        decision.outcome.value, decision.source_engine,
                        decision.venue, decision.reason, decision.ts_ns,
                    ),
                )
                conn.commit()
        except Exception as exc:
            _logger.warning("ExecutionAuditor: persist error: %s", exc)

    @staticmethod
    def _emit_anomaly(anomaly: AnomalyReport) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_VIOLATION, {
                "source": "execution_auditor",
                "hazard": anomaly.kind,
                "symbol": anomaly.symbol,
                "detail": anomaly.detail,
                "severity": "WARNING",
                "ts_ns": anomaly.ts_ns,
            })
        except Exception:
            pass
        try:
            from state.ledger.append import append_event
            append_event(
                stream="GOVERNANCE",
                kind="EXECUTION_ANOMALY",
                source="governance_engine",
                payload={
                    "kind": anomaly.kind,
                    "symbol": anomaly.symbol,
                    "detail": anomaly.detail,
                    "ts_ns": anomaly.ts_ns,
                },
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: tuple) -> dict[str, Any]:
    return {
        "decision_id":   row[0],
        "symbol":        row[1],
        "side":          row[2],
        "quantity":      row[3],
        "price":         row[4],
        "notional_usd":  row[5],
        "outcome":       row[6],
        "source_engine": row[7],
        "venue":         row[8],
        "reason":        row[9],
        "ts_ns":         row[10],
    }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_auditor: ExecutionAuditor | None = None
_auditor_lock = threading.Lock()


def get_execution_auditor(
    *, db_path: Path | str = _DEFAULT_DB, row_limit: int = 500
) -> ExecutionAuditor:
    global _auditor
    with _auditor_lock:
        if _auditor is None:
            _auditor = ExecutionAuditor(db_path=db_path, row_limit=row_limit)
    return _auditor


__all__ = [
    "AnomalyReport",
    "AuditOutcome",
    "BURST_MAX_FILLS",
    "ExecutionAuditor",
    "ExecutionDecision",
    "FILL_FREQ_MAX_PER_MIN",
    "NOTIONAL_ANOMALY_USD",
    "get_execution_auditor",
]
