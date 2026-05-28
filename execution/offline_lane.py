"""[NEW v1] — buffered offline lane for SystemEvent coordination.

The offline lane buffers SYSTEM events for offline engine consumption.
Drainable in batch — offline engines pull when ready rather than being
pushed. Only SYSTEM events are accepted.

B1:       No imports from engine tiers.
B27/B28:  Never constructs typed events.
INV-15:   Drain order is FIFO; deterministic for a given input sequence.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable

from core.contracts.events import EventKind, SystemEvent

__all__ = ["OfflineLane", "OfflineLaneHandler", "get_offline_lane"]

OfflineLaneHandler = Callable[[SystemEvent], None]


class OfflineLane:
    """FIFO buffer for SystemEvent (offline coordination lane).

    Offline engines call ``drain()`` at their own cadence. Push-based
    handlers may also be registered for immediate delivery.
    """

    def __init__(self, maxsize: int = 100_000) -> None:
        self._buffer: deque[SystemEvent] = deque(maxlen=maxsize)
        self._handlers: list[OfflineLaneHandler] = []
        self._lock = threading.Lock()
        self._emitted = 0
        self._dropped = 0

    def subscribe(self, handler: OfflineLaneHandler) -> None:
        with self._lock:
            self._handlers.append(handler)

    def emit(self, event: SystemEvent) -> bool:
        if event.kind is not EventKind.SYSTEM:
            return False
        with self._lock:
            if len(self._buffer) >= (self._buffer.maxlen or 100_000):
                self._dropped += 1
                return False
            self._buffer.append(event)
            self._emitted += 1
            handlers = list(self._handlers)
        for h in handlers:
            try:
                h(event)
            except Exception:  # noqa: BLE001
                pass
        return True

    def drain(self) -> tuple[SystemEvent, ...]:
        """Remove and return all buffered events (FIFO order)."""
        with self._lock:
            batch = tuple(self._buffer)
            self._buffer.clear()
        return batch

    def peek(self) -> tuple[SystemEvent, ...]:
        """Return buffered events without removing them."""
        with self._lock:
            return tuple(self._buffer)

    @property
    def emitted(self) -> int:
        return self._emitted

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._buffer)


_lane: OfflineLane | None = None
_lane_lock = threading.Lock()


def get_offline_lane() -> OfflineLane:
    global _lane
    if _lane is None:
        with _lane_lock:
            if _lane is None:
                _lane = OfflineLane()
    return _lane
