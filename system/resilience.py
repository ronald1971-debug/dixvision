"""system.resilience — circuit breaker registry.

Provides named circuit breakers. Each breaker transitions
CLOSED → OPEN when its error count exceeds the threshold, and
HALF_OPEN after a cooldown period. Callers check :meth:`is_open`
before attempting a remote call and report success/failure to
drive the state machine.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class BreakerState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreaker:
    name: str
    error_threshold: int = 5
    cooldown_ns: int = 30_000_000_000  # 30 s

    _state: BreakerState = field(default=BreakerState.CLOSED, init=False)
    _error_count: int = field(default=0, init=False)
    _opened_at_ns: int = field(default=0, init=False)

    def is_open(self, now_ns: int) -> bool:
        if self._state is BreakerState.CLOSED:
            return False
        if self._state is BreakerState.OPEN:
            if now_ns - self._opened_at_ns >= self.cooldown_ns:
                self._state = BreakerState.HALF_OPEN
                return False
            return True
        return False  # HALF_OPEN — allow one probe

    def record_success(self) -> None:
        self._error_count = 0
        self._state = BreakerState.CLOSED

    def record_failure(self, now_ns: int) -> None:
        self._error_count += 1
        if self._error_count >= self.error_threshold:
            self._state = BreakerState.OPEN
            self._opened_at_ns = now_ns

    def state(self) -> BreakerState:
        return self._state


class ResilienceCoordinator:
    """Registry of named circuit breakers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        *,
        error_threshold: int = 5,
        cooldown_ns: int = 30_000_000_000,
    ) -> CircuitBreaker:
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(
                    name=name,
                    error_threshold=error_threshold,
                    cooldown_ns=cooldown_ns,
                )
            return self._breakers[name]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                name: {"state": b.state().value, "errors": b._error_count}
                for name, b in self._breakers.items()
            }


_coordinator: ResilienceCoordinator | None = None
_lock = threading.Lock()


def get_resilience_coordinator() -> ResilienceCoordinator:
    global _coordinator
    if _coordinator is None:
        with _lock:
            if _coordinator is None:
                _coordinator = ResilienceCoordinator()
    return _coordinator
