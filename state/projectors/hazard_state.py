"""state.projectors.hazard_state — Hazard State Projector.

Build Plan §2.3: hazard_state projector — materialised view of active
and historical hazard events for governance and observability consumers.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from system import time_source


@dataclass(slots=True)
class HazardSnapshot:
    active_hazards: list[dict[str, Any]] = field(default_factory=list)
    total_count: int = 0
    last_hazard_ts_ns: int = 0
    current_severity: str = "NONE"


class HazardStateProjector:
    """Projects SYSTEM_HAZARD events into a queryable snapshot."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = HazardSnapshot()
        self._max_active = 100

    def apply(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("event_type", ""))
        if event_type != "HAZARD":
            return
        payload = event.get("payload", event)
        with self._lock:
            self._snapshot.total_count += 1
            self._snapshot.last_hazard_ts_ns = payload.get("ts_ns", time_source.wall_ns())
            entry = {
                "hazard_type": payload.get("hazard_type", "UNKNOWN"),
                "severity": payload.get("severity", "MEDIUM"),
                "source": payload.get("source", ""),
                "ts_ns": self._snapshot.last_hazard_ts_ns,
            }
            self._snapshot.active_hazards.append(entry)
            if len(self._snapshot.active_hazards) > self._max_active:
                self._snapshot.active_hazards = self._snapshot.active_hazards[-self._max_active :]
            self._snapshot.current_severity = self._highest_severity()

    def _highest_severity(self) -> str:
        order = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        best = "NONE"
        cutoff = time_source.wall_ns() - 60_000_000_000  # 60s window
        for h in self._snapshot.active_hazards:
            if h.get("ts_ns", 0) >= cutoff:
                sev = h.get("severity", "MEDIUM")
                if order.get(sev, 0) > order.get(best, 0):
                    best = sev
        return best

    def get_snapshot(self) -> HazardSnapshot:
        with self._lock:
            return HazardSnapshot(
                active_hazards=list(self._snapshot.active_hazards),
                total_count=self._snapshot.total_count,
                last_hazard_ts_ns=self._snapshot.last_hazard_ts_ns,
                current_severity=self._snapshot.current_severity,
            )


_projector: HazardStateProjector | None = None
_lock = threading.Lock()


def get_hazard_state_projector() -> HazardStateProjector:
    global _projector
    if _projector is None:
        with _lock:
            if _projector is None:
                _projector = HazardStateProjector()
    return _projector
