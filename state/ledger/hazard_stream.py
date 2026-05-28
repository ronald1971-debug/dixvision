"""state.ledger.hazard_stream — Dedicated SYSTEM_HAZARD event stream.

Build Plan §2.2: hazard_stream.py — dedicated stream for hazard events
with classification tagging. Routes through the StreamRouter so projectors
and governance can subscribe to SYSTEM_HAZARD events independently.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from state.ledger.event_store import append_event
from state.ledger.stream_router import get_stream_router
from system import time_source

HAZARD_STREAM = "SYSTEM_HAZARD"


@dataclass(frozen=True, slots=True)
class HazardStreamEntry:
    hazard_type: str
    severity: str
    source: str
    classification: str = "UNCLASSIFIED"
    details: dict[str, Any] = field(default_factory=dict)
    ts_ns: int = field(default_factory=time_source.wall_ns)


class HazardStream:
    """Append-only hazard event stream backed by the main event ledger."""

    def __init__(self) -> None:
        self._router = get_stream_router()
        self._lock = threading.Lock()
        self._count = 0

    def record(self, entry: HazardStreamEntry) -> int:
        payload = {
            "hazard_type": entry.hazard_type,
            "severity": entry.severity,
            "source": entry.source,
            "classification": entry.classification,
            "details": entry.details,
            "ts_ns": entry.ts_ns,
        }
        try:
            append_event(HAZARD_STREAM, entry.hazard_type, entry.source, payload)
        except Exception:
            pass
        self._router.publish(
            {
                "event_type": HAZARD_STREAM,
                "sub_type": entry.hazard_type,
                "payload": payload,
            }
        )
        with self._lock:
            self._count += 1
            return self._count

    @property
    def count(self) -> int:
        with self._lock:
            return self._count


_stream: HazardStream | None = None
_lock = threading.Lock()


def get_hazard_stream() -> HazardStream:
    global _stream
    if _stream is None:
        with _lock:
            if _stream is None:
                _stream = HazardStream()
    return _stream
