"""execution.system_repair_orchestrator — repair action coordinator.

When a hazard detector or circuit breaker signals an execution-tier
failure, the orchestrator maps the failure kind to a registered repair
callable and invokes it. Repair attempts are bounded and logged.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class RepairRecord:
    failure_kind: str
    attempts: int = 0
    last_outcome: str = "pending"  # "ok" | "failed" | "pending"
    last_error: str = ""


class SystemRepairOrchestrator:
    """Maps failure kinds to repair callables; bounded retry with audit."""

    MAX_ATTEMPTS = 3

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handlers: dict[str, Callable[[], None]] = {}
        self._records: dict[str, RepairRecord] = {}

    def register(self, failure_kind: str, handler: Callable[[], None]) -> None:
        with self._lock:
            self._handlers[failure_kind] = handler

    def repair(self, failure_kind: str) -> bool:
        """Invoke the registered handler for ``failure_kind``.

        Returns ``True`` when the repair succeeded or no handler is
        registered. Returns ``False`` on handler exception or when the
        per-kind attempt cap has been reached.
        """
        with self._lock:
            handler = self._handlers.get(failure_kind)
            rec = self._records.setdefault(failure_kind, RepairRecord(failure_kind=failure_kind))
            if rec.attempts >= self.MAX_ATTEMPTS:
                return False
            rec.attempts += 1

        if handler is None:
            with self._lock:
                self._records[failure_kind].last_outcome = "ok"
            return True

        try:
            handler()
            with self._lock:
                self._records[failure_kind].last_outcome = "ok"
            return True
        except Exception as exc:  # noqa: BLE001 - repair handlers may throw
            with self._lock:
                rec = self._records[failure_kind]
                rec.last_outcome = "failed"
                rec.last_error = str(exc)
            return False

    def reset(self, failure_kind: str) -> None:
        with self._lock:
            self._records.pop(failure_kind, None)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                k: {"attempts": r.attempts, "outcome": r.last_outcome}
                for k, r in self._records.items()
            }


_orchestrator: SystemRepairOrchestrator | None = None
_lock = threading.Lock()


def get_repair_orchestrator() -> SystemRepairOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        with _lock:
            if _orchestrator is None:
                _orchestrator = SystemRepairOrchestrator()
    return _orchestrator
