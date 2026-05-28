"""system.power_manager — compute resource budget manager.

Tracks per-subsystem CPU-time and memory usage. Heavy subsystems
(intelligence engine inference, evolution engine training, sensory
crawlers) register their resource consumption so the power manager can
throttle low-priority work when the system is under load.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class ResourceUsage:
    subsystem: str
    cpu_ms: float = 0.0
    memory_mb: float = 0.0
    throttled: bool = False


class PowerManager:
    """Thread-safe compute budget tracker and throttle switch."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._usage: dict[str, ResourceUsage] = {}

    def report(
        self,
        subsystem: str,
        *,
        cpu_ms: float = 0.0,
        memory_mb: float = 0.0,
    ) -> None:
        with self._lock:
            u = self._usage.setdefault(subsystem, ResourceUsage(subsystem=subsystem))
            u.cpu_ms += cpu_ms
            u.memory_mb = memory_mb  # snapshot value, not cumulative

    def is_throttled(self, subsystem: str) -> bool:
        with self._lock:
            u = self._usage.get(subsystem)
            return u.throttled if u else False

    def throttle(self, subsystem: str, throttled: bool) -> None:
        with self._lock:
            u = self._usage.setdefault(subsystem, ResourceUsage(subsystem=subsystem))
            u.throttled = throttled

    def reset_counters(self) -> None:
        """Reset rolling CPU counters (call once per accounting window)."""
        with self._lock:
            for u in self._usage.values():
                u.cpu_ms = 0.0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                sub: {
                    "cpu_ms": round(u.cpu_ms, 2),
                    "memory_mb": round(u.memory_mb, 2),
                    "throttled": u.throttled,
                }
                for sub, u in self._usage.items()
            }


_manager: PowerManager | None = None
_lock = threading.Lock()


def get_power_manager() -> PowerManager:
    global _manager
    if _manager is None:
        with _lock:
            if _manager is None:
                _manager = PowerManager()
    return _manager
