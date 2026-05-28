"""PLUGIN-ACT-07 — Hot-reload signal bus.

Append-only, thread-safe in-memory queue of reload signals.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReloadSignal:
    """Immutable hot-reload request for a single plugin."""

    plugin_id: str
    ts_ns: int
    reason: str = ""


class HotReloadBus:
    """Thread-safe append-only queue of :class:`ReloadSignal` objects.

    ``drain()`` atomically returns all pending signals and clears the queue.
    """

    __slots__ = ("_queue", "_lock")

    def __init__(self) -> None:
        self._queue: list[ReloadSignal] = []
        self._lock: threading.Lock = threading.Lock()

    def signal(self, plugin_id: str, ts_ns: int, reason: str = "") -> ReloadSignal:
        """Append a reload signal and return it."""
        sig = ReloadSignal(plugin_id=plugin_id, ts_ns=ts_ns, reason=reason)
        with self._lock:
            self._queue.append(sig)
        return sig

    def drain(self) -> tuple[ReloadSignal, ...]:
        """Return all pending signals and clear the queue (atomic)."""
        with self._lock:
            pending = tuple(self._queue)
            self._queue.clear()
        return pending


__all__ = ["ReloadSignal", "HotReloadBus"]
