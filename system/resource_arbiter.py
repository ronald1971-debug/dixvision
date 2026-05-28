"""system.resource_arbiter — resource allocation arbiter.

Arbitrates compute and I/O slots between competing subsystems using a
fixed-priority scheme. High-priority subsystems (execution, governance,
kill-switch) always get their slot; lower-priority subsystems
(learning, evolution, sensory crawlers) are admitted only when
head-room exists.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class ResourceSlot:
    subsystem: str
    priority: int  # lower integer = higher priority
    max_concurrent: int
    current: int = 0


class ResourceArbiter:
    """Token-based concurrency limiter with priority tiers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._slots: dict[str, ResourceSlot] = {}

    def register(
        self,
        subsystem: str,
        *,
        priority: int,
        max_concurrent: int,
    ) -> None:
        with self._lock:
            self._slots[subsystem] = ResourceSlot(
                subsystem=subsystem,
                priority=priority,
                max_concurrent=max_concurrent,
            )

    def acquire(self, subsystem: str) -> bool:
        """Request one slot. Returns ``True`` when admitted."""
        with self._lock:
            slot = self._slots.get(subsystem)
            if slot is None:
                return True  # unregistered — always admitted
            if slot.current < slot.max_concurrent:
                slot.current += 1
                return True
            return False

    def release(self, subsystem: str) -> None:
        with self._lock:
            slot = self._slots.get(subsystem)
            if slot and slot.current > 0:
                slot.current -= 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                s: {
                    "priority": sl.priority,
                    "current": sl.current,
                    "max": sl.max_concurrent,
                }
                for s, sl in self._slots.items()
            }


_arbiter: ResourceArbiter | None = None
_lock = threading.Lock()


def get_resource_arbiter() -> ResourceArbiter:
    global _arbiter
    if _arbiter is None:
        with _lock:
            if _arbiter is None:
                _arbiter = ResourceArbiter()
    return _arbiter
