"""execution.runtime_monitor — live execution-path health monitor.

Tracks adapter connectivity status, order dispatch throughput, and
per-adapter error counts so the health monitor and dashboard can
surface execution-tier issues without querying exchange APIs.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class AdapterHealth:
    adapter_id: str
    connected: bool = False
    orders_sent: int = 0
    errors: int = 0
    last_error: str = ""


class RuntimeMonitor:
    """Thread-safe execution-tier health tracker."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._adapters: dict[str, AdapterHealth] = {}
        self._total_orders: int = 0
        self._total_errors: int = 0

    def report_connected(self, adapter_id: str, connected: bool) -> None:
        with self._lock:
            h = self._adapters.setdefault(adapter_id, AdapterHealth(adapter_id=adapter_id))
            h.connected = connected

    def record_order(self, adapter_id: str) -> None:
        with self._lock:
            h = self._adapters.setdefault(adapter_id, AdapterHealth(adapter_id=adapter_id))
            h.orders_sent += 1
            self._total_orders += 1

    def record_error(self, adapter_id: str, error: str = "") -> None:
        with self._lock:
            h = self._adapters.setdefault(adapter_id, AdapterHealth(adapter_id=adapter_id))
            h.errors += 1
            h.last_error = error
            self._total_errors += 1

    def is_healthy(self) -> bool:
        with self._lock:
            if not self._adapters:
                return True
            return any(h.connected for h in self._adapters.values())

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_orders": self._total_orders,
                "total_errors": self._total_errors,
                "adapters": {
                    aid: {"connected": h.connected, "orders": h.orders_sent, "errors": h.errors}
                    for aid, h in self._adapters.items()
                },
            }


_monitor: RuntimeMonitor | None = None
_lock = threading.Lock()


def get_runtime_monitor() -> RuntimeMonitor:
    global _monitor
    if _monitor is None:
        with _lock:
            if _monitor is None:
                _monitor = RuntimeMonitor()
    return _monitor
