"""EXEC-05 — canonical single event bus (shared infrastructure).

Routes all four typed events (INV-08) to registered handlers.
Non-blocking emit; handlers run on a dedicated daemon thread.

B1:         No imports from engine tiers.
B27/B28:    Never constructs typed events — pure router.
INV-15:     Dispatch order is deterministic for a given queue sequence.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from core.contracts.events import Event, EventKind

__all__ = ["AsyncBus", "BusHandler", "BusSubscription", "get_async_bus"]

BusHandler = Callable[[Event], None]

_ALL_KINDS: Final[frozenset[EventKind]] = frozenset(EventKind)


@dataclass(slots=True)
class BusSubscription:
    handler: BusHandler
    kinds: frozenset[EventKind] = field(default_factory=lambda: _ALL_KINDS)


class AsyncBus:
    """Non-blocking multi-kind event bus (EXEC-05).

    Thread-safe: emit() is safe from any thread. Handlers run
    sequentially on a single daemon worker thread so ordering
    within a kind is preserved.
    """

    def __init__(self, maxsize: int = 50_000) -> None:
        self._q: queue.Queue[Event] = queue.Queue(maxsize=maxsize)
        self._subscriptions: list[BusSubscription] = []
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._running = False
        self._dropped = 0

    def start(self) -> None:
        self._running = True
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(
            target=self._dispatch_loop, daemon=True, name="AsyncBus"
        )
        self._worker.start()

    def stop(self) -> None:
        self._running = False

    def subscribe(
        self,
        handler: BusHandler,
        *,
        kinds: frozenset[EventKind] | None = None,
    ) -> None:
        ks = kinds if kinds is not None else _ALL_KINDS
        with self._lock:
            self._subscriptions.append(BusSubscription(handler=handler, kinds=ks))

    def emit(self, event: Event) -> bool:
        """Non-blocking emit. Returns False when queue is full (drop)."""
        try:
            self._q.put_nowait(event)
            return True
        except queue.Full:
            self._dropped += 1
            return False

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def qsize(self) -> int:
        return self._q.qsize()

    def _dispatch_loop(self) -> None:
        while self._running:
            try:
                event = self._q.get(timeout=0.05)
                self._route(event)
            except queue.Empty:
                continue
            except Exception:  # noqa: BLE001
                continue

    def _route(self, event: Event) -> None:
        with self._lock:
            subs = list(self._subscriptions)
        for sub in subs:
            if event.kind in sub.kinds:
                try:
                    sub.handler(event)
                except Exception:  # noqa: BLE001
                    pass


_bus: AsyncBus | None = None
_bus_lock = threading.Lock()


def get_async_bus() -> AsyncBus:
    """Return the process-wide :class:`AsyncBus` singleton."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = AsyncBus()
                _bus.start()
    return _bus
