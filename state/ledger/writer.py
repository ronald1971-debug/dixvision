"""
state/ledger/writer.py
Async write pipeline over the EventStore. Callers enqueue events; a background
thread drains and appends. Non-blocking on the hot path.

If the queue is full the write is executed synchronously — losing an event is
not acceptable (integrity > latency). This matches the manifest's "ledger failure
never blocks detection" constraint while keeping durability.

Circuit breaker (INV-65):
After LEDGER_FAIL_THRESHOLD consecutive write failures the writer sets
``_degraded = True`` and triggers the kill switch. Trading without an audit
trail violates INV-65 (ledger integrity). Any successful write resets the
consecutive-failure counter.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Any

_logger = logging.getLogger(__name__)

from state.ledger.event_store import append_event
from state.ledger.stream_router import get_stream_router

# Number of consecutive write failures that trigger the kill switch.
LEDGER_FAIL_THRESHOLD: int = 10


@dataclass
class _WriteJob:
    event_type: str
    sub_type: str
    source: str
    payload: dict[str, Any]


class AsyncWriter:
    def __init__(self, maxsize: int = 10_000) -> None:
        self._q: queue.Queue[_WriteJob] = queue.Queue(maxsize=maxsize)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._router = get_stream_router()
        self._consecutive_failures: int = 0
        self._degraded: bool = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="DIX-LedgerWriter")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def is_healthy(self) -> bool:
        """Return False when the ledger circuit breaker has tripped."""
        return not self._degraded

    def write(self, event_type: str, sub_type: str, source: str, payload: dict[str, Any]) -> bool:
        job = _WriteJob(event_type, sub_type, source, payload)
        try:
            self._q.put_nowait(job)
            return True
        except queue.Full:
            self._append_and_route(job)
            return True

    def append_event(
        self,
        *,
        stream: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        source: str = "system",
    ) -> bool:
        """Convenience alias using (stream, kind) naming.

        Maps to :meth:`write` as event_type=stream, sub_type=kind. Keeps
        callers in governance + pairing + worker from having to know the
        lower-level event_type/sub_type vocabulary.
        """
        return self.write(stream, kind, source, payload or {})

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._q.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._append_and_route(job)
                # Successful write — reset the consecutive-failure counter.
                self._consecutive_failures = 0
            except Exception as exc:
                self._consecutive_failures += 1
                _logger.error(
                    "LedgerWriter: write failed for %s/%s (consecutive=%d): %s",
                    job.event_type, job.sub_type, self._consecutive_failures, exc,
                    exc_info=True,
                )
                if self._consecutive_failures >= LEDGER_FAIL_THRESHOLD and not self._degraded:
                    self._degraded = True
                    _logger.critical(
                        "LedgerWriter: %d consecutive failures — ledger is DOWN. "
                        "Trading without an audit trail violates INV-65. "
                        "Activating kill switch.",
                        self._consecutive_failures,
                    )
                    try:
                        from immutable_core.kill_switch import trigger_kill_switch
                        trigger_kill_switch(
                            reason=f"LedgerWriter: {self._consecutive_failures} "
                                   "consecutive ledger write failures (INV-65)",
                            source="LedgerWriter",
                        )
                    except Exception as ks_exc:
                        _logger.critical("LedgerWriter: kill switch activation failed: %s", ks_exc)
                continue

    def _append_and_route(self, job: _WriteJob) -> None:
        ev = append_event(job.event_type, job.sub_type, job.source, job.payload)
        self._router.publish(
            {
                "event_type": job.event_type,
                "sub_type": job.sub_type,
                "source": job.source,
                "payload": job.payload,
                "event_id": getattr(ev, "event_id", None),
                "sequence": getattr(ev, "sequence", None),
                "event_hash": getattr(ev, "event_hash", None),
            }
        )


_writer: AsyncWriter | None = None
_lock = threading.Lock()


def get_writer() -> AsyncWriter:
    global _writer
    if _writer is None:
        with _lock:
            if _writer is None:
                _writer = AsyncWriter()
                _writer.start()
    return _writer
