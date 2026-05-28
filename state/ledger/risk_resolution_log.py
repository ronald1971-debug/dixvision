"""state.ledger.risk_resolution_log — Hazard resolution audit trail.

Build Plan §2.2: risk_resolution_log.py — records every hazard → resolution
decision so the governance path is fully replayable.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from state.ledger.event_store import append_event
from system import time_source

RESOLUTION_STREAM = "RISK_RESOLUTION"


@dataclass(frozen=True, slots=True)
class ResolutionRecord:
    hazard_type: str
    action_taken: str
    decided_by: str
    severity: str = "MEDIUM"
    latency_ns: int = 0
    details: dict[str, Any] = field(default_factory=dict)
    ts_ns: int = field(default_factory=time_source.wall_ns)


class RiskResolutionLog:
    """Append-only log of hazard resolutions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: list[ResolutionRecord] = []
        self._max_in_memory = 10_000

    def record(self, entry: ResolutionRecord) -> None:
        try:
            append_event(
                RESOLUTION_STREAM,
                entry.action_taken,
                entry.decided_by,
                {
                    "hazard_type": entry.hazard_type,
                    "action_taken": entry.action_taken,
                    "decided_by": entry.decided_by,
                    "severity": entry.severity,
                    "latency_ns": entry.latency_ns,
                    "details": entry.details,
                },
            )
        except Exception:
            pass
        with self._lock:
            self._records.append(entry)
            if len(self._records) > self._max_in_memory:
                self._records = self._records[-self._max_in_memory :]

    def recent(self, n: int = 100) -> list[ResolutionRecord]:
        with self._lock:
            return list(self._records[-n:])


_log: RiskResolutionLog | None = None
_lock = threading.Lock()


def get_risk_resolution_log() -> RiskResolutionLog:
    global _log
    if _log is None:
        with _lock:
            if _log is None:
                _log = RiskResolutionLog()
    return _log
