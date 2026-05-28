"""[NEW v1] — segmented hot-path bus for SIGNAL + EXECUTION events.

The fast lane is a synchronous, zero-copy dispatcher for latency-
sensitive events. Handlers are called on the emitter's thread so
there is no queue overhead. Only SIGNAL and EXECUTION events are
accepted (INV-08 hot path subset).

B1:       No imports from engine tiers.
B27/B28:  Never constructs typed events.
INV-15:   Registration order is deterministic.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Final

from core.contracts.events import EventKind, ExecutionEvent, SignalEvent

__all__ = ["FastLane", "FastLaneHandler", "get_fast_lane"]

FastLaneHandler = Callable[[SignalEvent | ExecutionEvent], None]

_HOT_KINDS: Final[frozenset[EventKind]] = frozenset(
    {EventKind.SIGNAL, EventKind.EXECUTION}
)


class FastLane:
    """Synchronous hot-path lane for SIGNAL + EXECUTION events.

    Handlers are called in registration order on the emitting thread.
    No queue, no thread hops — designed for sub-microsecond dispatch.
    """

    def __init__(self) -> None:
        self._handlers: list[FastLaneHandler] = []
        self._lock = threading.Lock()
        self._emitted = 0
        self._rejected = 0

    def subscribe(self, handler: FastLaneHandler) -> None:
        with self._lock:
            self._handlers.append(handler)

    def emit(self, event: SignalEvent | ExecutionEvent) -> bool:
        """Synchronous emit. Returns False if event kind not accepted."""
        if event.kind not in _HOT_KINDS:
            self._rejected += 1
            return False
        self._emitted += 1
        with self._lock:
            handlers = list(self._handlers)
        for h in handlers:
            try:
                h(event)
            except Exception:  # noqa: BLE001
                pass
        return True

    @property
    def emitted(self) -> int:
        return self._emitted

    @property
    def rejected(self) -> int:
        return self._rejected


_lane: FastLane | None = None
_lane_lock = threading.Lock()


def get_fast_lane() -> FastLane:
    global _lane
    if _lane is None:
        with _lane_lock:
            if _lane is None:
                _lane = FastLane()
    return _lane
