"""GOV-G09 — Liveness watchdog.

Tracks per-engine heartbeat timestamps and classifies engines as
ALIVE / STALE / DEAD. Pure function of inputs — never reads wall clock (INV-15).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

_NS_30S = 30_000_000_000
_NS_120S = 120_000_000_000


class LivenessStatus(StrEnum):
    ALIVE = "ALIVE"
    STALE = "STALE"
    DEAD = "DEAD"


@dataclass(frozen=True, slots=True)
class EngineHeartbeat:
    """Immutable heartbeat record from an engine."""

    engine_id: str
    ts_ns: int


class LivenessWatchdog:
    """Per-engine liveness classifier.

    All time is supplied by the caller via ``now_ns`` — no wall-clock reads.
    """

    __slots__ = ("stale_threshold_ns", "dead_threshold_ns", "_last")

    def __init__(
        self,
        stale_threshold_ns: int = _NS_30S,
        dead_threshold_ns: int = _NS_120S,
    ) -> None:
        self.stale_threshold_ns = stale_threshold_ns
        self.dead_threshold_ns = dead_threshold_ns
        self._last: dict[str, int] = {}

    # ------------------------------------------------------------------
    def record(self, heartbeat: EngineHeartbeat) -> None:
        """Record the most recent heartbeat for an engine."""
        self._last[heartbeat.engine_id] = heartbeat.ts_ns

    def status(self, engine_id: str, *, now_ns: int) -> LivenessStatus:
        """Return the liveness status of *engine_id* at *now_ns*."""
        last_ns = self._last.get(engine_id)
        if last_ns is None:
            return LivenessStatus.DEAD
        elapsed = now_ns - last_ns
        if elapsed >= self.dead_threshold_ns:
            return LivenessStatus.DEAD
        if elapsed >= self.stale_threshold_ns:
            return LivenessStatus.STALE
        return LivenessStatus.ALIVE

    def all_statuses(self, *, now_ns: int) -> dict[str, LivenessStatus]:
        """Return a status snapshot for every tracked engine."""
        return {eid: self.status(eid, now_ns=now_ns) for eid in self._last}


__all__ = ["LivenessStatus", "EngineHeartbeat", "LivenessWatchdog"]
