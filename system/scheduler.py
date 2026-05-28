"""system.scheduler — periodic task scheduler.

Maintains a registry of named periodic tasks (heartbeats, snapshot
triggers, data-quality sweeps). Each task has a minimum interval;
:meth:`tick` is called by the system loop and fires tasks whose
interval has elapsed. No threads are spawned here — the caller's
event loop drives :meth:`tick`.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class ScheduledTask:
    name: str
    fn: Callable[[], None]
    interval_ns: int
    last_run_ns: int = 0


class Scheduler:
    """Registry-driven periodic task runner (caller-driven tick)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, ScheduledTask] = {}

    def register(
        self,
        name: str,
        fn: Callable[[], None],
        *,
        interval_ns: int,
    ) -> None:
        with self._lock:
            self._tasks[name] = ScheduledTask(name=name, fn=fn, interval_ns=interval_ns)

    def unregister(self, name: str) -> None:
        with self._lock:
            self._tasks.pop(name, None)

    def tick(self, now_ns: int) -> list[str]:
        """Fire all tasks whose interval has elapsed since their last run.

        Returns the names of tasks that were invoked. Task exceptions
        are swallowed so one bad task never aborts the tick loop.
        """
        with self._lock:
            due = [t for t in self._tasks.values() if now_ns - t.last_run_ns >= t.interval_ns]

        fired: list[str] = []
        for task in due:
            try:
                task.fn()
            except Exception:  # noqa: BLE001 - never abort the tick loop
                pass
            with self._lock:
                task.last_run_ns = now_ns
            fired.append(task.name)
        return fired

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                name: {"interval_ns": t.interval_ns, "last_run_ns": t.last_run_ns}
                for name, t in self._tasks.items()
            }


_scheduler: Scheduler | None = None
_lock = threading.Lock()


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        with _lock:
            if _scheduler is None:
                _scheduler = Scheduler()
    return _scheduler
