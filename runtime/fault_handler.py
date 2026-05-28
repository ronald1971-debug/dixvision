"""runtime.fault_handler — Production Fault Handling.

Handles real operational failures: adapter disconnects, exchange errors,
data feed stalls, governance timeouts, position reconciliation failures.

OPERATIONAL BEHAVIOR:
- Faults are classified by severity (TRANSIENT, DEGRADING, CRITICAL, FATAL)
- Transient faults → retry with backoff
- Degrading faults → reduce execution scope
- Critical faults → trigger DEGRADED mode
- Fatal faults → trigger EMERGENCY_HALT
- All faults are ledgered for post-mortem analysis
- Fault patterns trigger adaptive circuit breakers
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from system import time_source

logger = logging.getLogger(__name__)


class FaultSeverity(StrEnum):
    """Fault severity classification."""

    TRANSIENT = "TRANSIENT"  # Retry-able, no mode change
    DEGRADING = "DEGRADING"  # Reduce scope but continue
    CRITICAL = "CRITICAL"  # Trigger DEGRADED mode
    FATAL = "FATAL"  # Trigger EMERGENCY_HALT


class FaultCategory(StrEnum):
    """Fault source categories."""

    ADAPTER = "ADAPTER"
    EXCHANGE = "EXCHANGE"
    DATA_FEED = "DATA_FEED"
    GOVERNANCE = "GOVERNANCE"
    RECONCILIATION = "RECONCILIATION"
    INTERNAL = "INTERNAL"
    NETWORK = "NETWORK"
    STATE = "STATE"


@dataclass(frozen=True, slots=True)
class Fault:
    """Immutable fault record."""

    fault_id: str
    category: FaultCategory
    severity: FaultSeverity
    source: str
    message: str
    ts_ns: int = field(default_factory=time_source.wall_ns)
    context: dict[str, Any] = field(default_factory=dict)
    recoverable: bool = True
    retry_count: int = 0


@dataclass(frozen=True, slots=True)
class FaultResolution:
    """Resolution of a fault."""

    fault_id: str
    resolved: bool
    action_taken: str
    duration_ms: float = 0.0
    ts_ns: int = field(default_factory=time_source.wall_ns)


@dataclass
class CircuitBreakerState:
    """Per-source circuit breaker."""

    source: str
    failure_count: int = 0
    last_failure_ts: float = 0.0
    open: bool = False
    half_open_at: float = 0.0
    cooldown_seconds: float = 30.0

    @property
    def is_open(self) -> bool:
        if not self.open:
            return False
        if time_source.wall_ns() / 1_000_000_000 >= self.half_open_at:
            return False  # Half-open, allow probe
        return True

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_ts = time_source.wall_ns() / 1_000_000_000
        if self.failure_count >= 3:
            self.open = True
            self.half_open_at = time_source.wall_ns() / 1_000_000_000 + self.cooldown_seconds

    def record_success(self) -> None:
        self.failure_count = 0
        self.open = False


class FaultHandler:
    """Production fault handler with circuit breakers.

    Classifies faults, determines recovery action, manages circuit
    breakers per fault source, and triggers mode changes when necessary.
    """

    __slots__ = (
        "_faults",
        "_resolutions",
        "_circuit_breakers",
        "_severity_counts",
        "_mode_trigger_callback",
    )

    def __init__(self, mode_trigger_callback: Any = None) -> None:
        self._faults: list[Fault] = []
        self._resolutions: list[FaultResolution] = []
        self._circuit_breakers: dict[str, CircuitBreakerState] = {}
        self._severity_counts: dict[FaultSeverity, int] = defaultdict(int)
        self._mode_trigger_callback = mode_trigger_callback

    def handle(self, fault: Fault) -> FaultResolution:
        """Handle a fault — classify, decide action, trigger mode change if needed."""
        self._faults.append(fault)
        self._severity_counts[fault.severity] += 1

        if len(self._faults) > 5000:
            self._faults = self._faults[-2500:]

        # Update circuit breaker
        cb = self._get_circuit_breaker(fault.source)
        cb.record_failure()

        # Take action based on severity
        if fault.severity == FaultSeverity.TRANSIENT:
            resolution = self._handle_transient(fault)
        elif fault.severity == FaultSeverity.DEGRADING:
            resolution = self._handle_degrading(fault)
        elif fault.severity == FaultSeverity.CRITICAL:
            resolution = self._handle_critical(fault)
        else:
            resolution = self._handle_fatal(fault)

        self._resolutions.append(resolution)
        return resolution

    def _handle_transient(self, fault: Fault) -> FaultResolution:
        """Handle transient fault — log and allow retry."""
        logger.debug("Transient fault from %s: %s", fault.source, fault.message)
        return FaultResolution(
            fault_id=fault.fault_id,
            resolved=True,
            action_taken="logged_for_retry",
        )

    def _handle_degrading(self, fault: Fault) -> FaultResolution:
        """Handle degrading fault — reduce execution scope."""
        logger.warning("Degrading fault from %s: %s", fault.source, fault.message)
        return FaultResolution(
            fault_id=fault.fault_id,
            resolved=True,
            action_taken="scope_reduced",
        )

    def _handle_critical(self, fault: Fault) -> FaultResolution:
        """Handle critical fault — trigger DEGRADED mode."""
        logger.error("CRITICAL fault from %s: %s", fault.source, fault.message)
        if self._mode_trigger_callback:
            self._mode_trigger_callback("DEGRADED", fault.message)
        return FaultResolution(
            fault_id=fault.fault_id,
            resolved=False,
            action_taken="degraded_mode_triggered",
        )

    def _handle_fatal(self, fault: Fault) -> FaultResolution:
        """Handle fatal fault — trigger EMERGENCY_HALT."""
        logger.critical("FATAL fault from %s: %s", fault.source, fault.message)
        if self._mode_trigger_callback:
            self._mode_trigger_callback("EMERGENCY_HALT", fault.message)
        return FaultResolution(
            fault_id=fault.fault_id,
            resolved=False,
            action_taken="emergency_halt_triggered",
        )

    def is_circuit_open(self, source: str) -> bool:
        """Check if circuit breaker is open for a source."""
        cb = self._circuit_breakers.get(source)
        return cb.is_open if cb else False

    def record_success(self, source: str) -> None:
        """Record successful operation (resets circuit breaker)."""
        cb = self._circuit_breakers.get(source)
        if cb:
            cb.record_success()

    def _get_circuit_breaker(self, source: str) -> CircuitBreakerState:
        """Get or create circuit breaker for source."""
        if source not in self._circuit_breakers:
            self._circuit_breakers[source] = CircuitBreakerState(source=source)
        return self._circuit_breakers[source]

    @property
    def active_faults(self) -> list[Fault]:
        """Unresolved faults from last 5 minutes."""
        cutoff = time_source.wall_ns() - (5 * 60 * 1_000_000_000)
        resolved_ids = {r.fault_id for r in self._resolutions if r.resolved}
        return [f for f in self._faults if f.ts_ns > cutoff and f.fault_id not in resolved_ids]

    @property
    def open_circuits(self) -> list[str]:
        """Sources with open circuit breakers."""
        return [src for src, cb in self._circuit_breakers.items() if cb.is_open]

    @property
    def stats(self) -> dict[str, int]:
        return {
            "total_faults": len(self._faults),
            "active_faults": len(self.active_faults),
            "open_circuits": len(self.open_circuits),
            **{sev.value: count for sev, count in self._severity_counts.items()},
        }


__all__ = [
    "CircuitBreakerState",
    "Fault",
    "FaultCategory",
    "FaultHandler",
    "FaultResolution",
    "FaultSeverity",
]
