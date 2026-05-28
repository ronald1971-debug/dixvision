"""observability.logs.log_sink — Structured log sink with in-process buffer.

Collects structured log records from subsystems and exposes them for
export (dashboard tail, OTLP log export, CI dump). No external I/O is
performed here; the sink is a pure in-memory buffer with a subscriber
model.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any

from system.time_source import monotonic_ns as _monotonic_ns


@dataclass(frozen=True, slots=True)
class LogRecord:
    """Normalized structured log record."""

    ts_ns: int
    level: str
    logger_name: str
    message: str
    extra: dict[str, Any]


class LogSink(logging.Handler):
    """Thread-safe structured log sink.

    Attach to any Python logger to capture records. Maintains a bounded
    deque so tail reads are O(1).
    """

    def __init__(self, maxlen: int = 5_000) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._records: deque[LogRecord] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            extra = {
                k: v
                for k, v in record.__dict__.items()
                if k not in logging.LogRecord.__dict__ and not k.startswith("_")
            }
            lr = LogRecord(
                ts_ns=_monotonic_ns(),
                level=record.levelname,
                logger_name=record.name,
                message=self.format(record),
                extra=extra,
            )
        except Exception:
            return
        with self._lock:
            self._records.append(lr)

    def tail(self, n: int = 100) -> list[LogRecord]:
        with self._lock:
            return list(self._records)[-n:]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._records)


_sink: LogSink | None = None
_lock = threading.Lock()


def get_log_sink(maxlen: int = 5_000) -> LogSink:
    """Get or create the process-level LogSink singleton."""
    global _sink
    if _sink is None:
        with _lock:
            if _sink is None:
                _sink = LogSink(maxlen=maxlen)
    return _sink


def install_global_sink(
    logger_name: str = "",
    level: int = logging.DEBUG,
) -> LogSink:
    """Install the singleton sink on the given Python logger (default: root)."""
    sink = get_log_sink()
    target = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    if sink not in target.handlers:
        sink.setLevel(level)
        target.addHandler(sink)
    return sink


__all__ = ["LogRecord", "LogSink", "get_log_sink", "install_global_sink"]
