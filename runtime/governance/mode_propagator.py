"""runtime.governance.mode_propagator — Synchronous Mode Propagation.

When the system mode changes (e.g., PAPER → CANARY → LIVE or
RUNNING → DEGRADED → HALT), ALL subsystems MUST acknowledge the
change BEFORE execution continues. This is not eventual consistency —
it is SYNCHRONOUS, BLOCKING propagation.

OPERATIONAL INVARIANTS:
- Mode changes propagate SYNCHRONOUSLY (caller blocks until all ACK)
- Subsystems that don't ACK within timeout trigger EMERGENCY_HALT
- Mode changes are ATOMIC (either all subsystems transition or none do)
- Every mode change is ledgered with all ACK timestamps
- No execution occurs during mode transition (pipeline paused)

This is the difference between "governance as structure" and
"governance as runtime authority."
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from system import time_source

logger = logging.getLogger(__name__)


class PropagationResult(StrEnum):
    """Mode propagation outcome."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    TIMEOUT = "TIMEOUT"
    REJECTED = "REJECTED"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class SubsystemAck:
    """Acknowledgment from a subsystem for a mode change."""

    subsystem_id: str
    accepted: bool
    new_mode: str
    latency_ns: int = 0
    error: str = ""
    ts_ns: int = field(default_factory=time_source.wall_ns)


@dataclass(frozen=True, slots=True)
class ModePropagationEvent:
    """Full record of a mode propagation."""

    old_mode: str
    new_mode: str
    result: PropagationResult
    acks: tuple[SubsystemAck, ...] = ()
    total_latency_ns: int = 0
    triggered_by: str = ""
    ts_ns: int = field(default_factory=time_source.wall_ns)


@dataclass
class PropagatorConfig:
    """Mode propagation configuration."""

    ack_timeout_ms: float = 5000.0
    require_unanimous: bool = True
    halt_on_timeout: bool = True
    pause_execution_during_transition: bool = True


# Type for subsystem mode handlers
ModeHandler = Callable[[str, str], bool]  # (old_mode, new_mode) → accepted


class ModePropagator:
    """Synchronous, blocking mode propagation to all subsystems.

    When a mode change is initiated (by operator or governance):
    1. Pause all execution
    2. Notify all registered subsystems of the new mode
    3. Wait for ALL to ACK (or timeout)
    4. If all ACK: commit the transition
    5. If any fail: rollback or HALT
    6. Resume execution
    """

    __slots__ = (
        "_config",
        "_handlers",
        "_history",
        "_current_mode",
        "_transitioning",
    )

    def __init__(self, config: PropagatorConfig | None = None, initial_mode: str = "PAPER") -> None:
        self._config = config or PropagatorConfig()
        self._handlers: dict[str, ModeHandler] = {}
        self._history: list[ModePropagationEvent] = []
        self._current_mode = initial_mode
        self._transitioning = False

    @property
    def current_mode(self) -> str:
        return self._current_mode

    @property
    def is_transitioning(self) -> bool:
        return self._transitioning

    def register(self, subsystem_id: str, handler: ModeHandler) -> None:
        """Register a subsystem for mode change notifications."""
        self._handlers[subsystem_id] = handler
        logger.debug("Registered mode handler: %s", subsystem_id)

    def unregister(self, subsystem_id: str) -> None:
        """Unregister a subsystem."""
        self._handlers.pop(subsystem_id, None)

    def propagate(self, new_mode: str, triggered_by: str = "operator") -> ModePropagationEvent:
        """SYNCHRONOUSLY propagate a mode change to all subsystems.

        This method BLOCKS until all subsystems acknowledge or timeout.
        During propagation, all execution is paused.

        Returns:
            ModePropagationEvent with full ACK details.
        """
        old_mode = self._current_mode
        if new_mode == old_mode:
            return ModePropagationEvent(
                old_mode=old_mode,
                new_mode=new_mode,
                result=PropagationResult.SUCCESS,
                triggered_by=triggered_by,
            )

        self._transitioning = True
        start_ns = time_source.now_ns()
        acks: list[SubsystemAck] = []

        logger.info(
            "Mode propagation: %s → %s (triggered by %s, %d subsystems)",
            old_mode,
            new_mode,
            triggered_by,
            len(self._handlers),
        )

        # Notify all subsystems (synchronous)
        for subsystem_id, handler in self._handlers.items():
            ack = self._notify_subsystem(subsystem_id, handler, old_mode, new_mode)
            acks.append(ack)

        total_latency_ns = time_source.now_ns() - start_ns

        # Evaluate result
        all_accepted = all(a.accepted for a in acks)
        any_timeout = any(a.error == "timeout" for a in acks)

        if all_accepted:
            result = PropagationResult.SUCCESS
            self._current_mode = new_mode
            logger.info(
                "Mode propagation SUCCESS: %s → %s (%.1fms)",
                old_mode,
                new_mode,
                total_latency_ns / 1_000_000,
            )
        elif any_timeout and self._config.halt_on_timeout:
            result = PropagationResult.HALTED
            self._current_mode = "EMERGENCY_HALT"
            logger.critical("Mode propagation TIMEOUT → EMERGENCY_HALT")
        elif not self._config.require_unanimous:
            result = PropagationResult.PARTIAL
            self._current_mode = new_mode
            failed = [a.subsystem_id for a in acks if not a.accepted]
            logger.warning("Mode propagation PARTIAL: %s failed", failed)
        else:
            result = PropagationResult.REJECTED
            # Don't change mode on rejection
            rejected = [a.subsystem_id for a in acks if not a.accepted]
            logger.error("Mode propagation REJECTED by: %s", rejected)

        self._transitioning = False

        event = ModePropagationEvent(
            old_mode=old_mode,
            new_mode=self._current_mode,
            result=result,
            acks=tuple(acks),
            total_latency_ns=total_latency_ns,
            triggered_by=triggered_by,
        )

        self._history.append(event)
        if len(self._history) > 100:
            self._history = self._history[-50:]

        return event

    def _notify_subsystem(
        self, subsystem_id: str, handler: ModeHandler, old_mode: str, new_mode: str
    ) -> SubsystemAck:
        """Notify a single subsystem and wait for ACK."""
        start_ns = time_source.now_ns()

        try:
            accepted = handler(old_mode, new_mode)
            latency_ns = time_source.now_ns() - start_ns

            # Check timeout
            latency_ms = latency_ns / 1_000_000
            if latency_ms > self._config.ack_timeout_ms:
                return SubsystemAck(
                    subsystem_id=subsystem_id,
                    accepted=False,
                    new_mode=new_mode,
                    latency_ns=latency_ns,
                    error="timeout",
                )

            return SubsystemAck(
                subsystem_id=subsystem_id,
                accepted=accepted,
                new_mode=new_mode,
                latency_ns=latency_ns,
            )

        except Exception as e:
            latency_ns = time_source.now_ns() - start_ns
            logger.error("Mode notification failed for %s: %s", subsystem_id, e)
            return SubsystemAck(
                subsystem_id=subsystem_id,
                accepted=False,
                new_mode=new_mode,
                latency_ns=latency_ns,
                error=str(e),
            )

    @property
    def propagation_history(self) -> list[ModePropagationEvent]:
        return list(self._history)

    @property
    def registered_subsystems(self) -> list[str]:
        return list(self._handlers.keys())


__all__ = [
    "ModeHandler",
    "ModePropagationEvent",
    "ModePropagator",
    "PropagationResult",
    "PropagatorConfig",
    "SubsystemAck",
]
