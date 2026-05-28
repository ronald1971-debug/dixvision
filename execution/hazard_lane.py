"""[NEW v1] — priority hazard lane for HazardEvent routing.

The hazard lane routes HAZARD events in severity order (CRITICAL first).
Non-blocking enqueue from emitter thread; handler thread dispatches in
priority order. Only HAZARD events are accepted.

B1:       No imports from engine tiers.
B27/B28:  Never constructs typed events.
INV-15:   Priority ordering is deterministic for identical inputs.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import Final

from core.contracts.events import EventKind, HazardEvent, HazardSeverity

__all__ = ["HazardLane", "HazardLaneHandler", "get_hazard_lane"]

HazardLaneHandler = Callable[[HazardEvent], None]

_SEVERITY_PRIORITY: Final[dict[HazardSeverity, int]] = {
    HazardSeverity.CRITICAL: 0,
    HazardSeverity.HIGH: 1,
    HazardSeverity.MEDIUM: 2,
    HazardSeverity.LOW: 3,
    HazardSeverity.INFO: 4,
}


class HazardLane:
    """Priority queue bus for HazardEvent (CRITICAL dispatched first)."""

    def __init__(self, maxsize: int = 10_000) -> None:
        self._q: queue.PriorityQueue[tuple[int, int, HazardEvent]] = (
            queue.PriorityQueue(maxsize=maxsize)
        )
        self._handlers: list[HazardLaneHandler] = []
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._running = False
        self._seq = 0
        self._dropped = 0

    def start(self) -> None:
        self._running = True
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(
            target=self._dispatch_loop, daemon=True, name="HazardLane"
        )
        self._worker.start()

    def stop(self) -> None:
        self._running = False

    def subscribe(self, handler: HazardLaneHandler) -> None:
        with self._lock:
            self._handlers.append(handler)

    def emit(self, event: HazardEvent) -> bool:
        if event.kind is not EventKind.HAZARD:
            return False
        priority = _SEVERITY_PRIORITY.get(event.severity, 99)
        with self._lock:
            seq = self._seq
            self._seq += 1
        try:
            self._q.put_nowait((priority, seq, event))
            return True
        except queue.Full:
            self._dropped += 1
            return False

    @property
    def dropped(self) -> int:
        return self._dropped

    def _dispatch_loop(self) -> None:
        while self._running:
            try:
                _, _, event = self._q.get(timeout=0.05)
                with self._lock:
                    handlers = list(self._handlers)
                for h in handlers:
                    try:
                        h(event)
                    except Exception:  # noqa: BLE001
                        pass
            except queue.Empty:
                continue
            except Exception:  # noqa: BLE001
                continue


_lane: HazardLane | None = None
_lane_lock = threading.Lock()


def get_hazard_lane() -> HazardLane:
    global _lane
    if _lane is None:
        with _lane_lock:
            if _lane is None:
                _lane = HazardLane()
                _lane.start()
    return _lane
