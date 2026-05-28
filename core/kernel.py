"""SystemKernel — the single canonical runtime state authority.

This is the architectural compression layer that owns exactly three things:

1. **Canonical BeliefState** — the ONE system-wide market+regime projection.
2. **System Mode FSM** — the ONE authoritative mode (PAPER/CANARY/LIVE/etc).
3. **Event Bus** — the ONE path for typed events between engines.

Everything else — intelligence, execution, governance, learning, evolution,
dashboards — is a **service** that reads from and writes to the kernel
through typed contracts. No service may hold its own authoritative state.

Design principles:
- The kernel is the ONLY writer of ``SystemMode`` transitions.
- The kernel is the ONLY writer of ``BeliefState`` snapshots.
- The kernel is the ONLY dispatcher of typed events to engine ``process()``.
- Services register via :meth:`register_service` and receive events
  through their ``process()`` method.
- UI widgets read kernel projections via :meth:`project` — never local mocks.

This replaces the previous architecture where ``ui/server.py._State``,
``runtime.kernel.RuntimeKernel``, and ``runtime.authority.RuntimeAuthorityStore``
all held partial, potentially conflicting views of system state.

Authority constraints:
- Only ``core.contracts`` and ``core.coherence`` imports.
- No engine-package imports (INV-08).
- Thread-safe via immutable snapshots + serialized writes.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Protocol

from core.coherence.belief_state import BeliefState, Regime
from core.contracts.events import Event, Side
from core.contracts.governance import SystemMode
from core.contracts.mode_effects import effect_for
from system.time_source import wall_ns

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Kernel State
# ---------------------------------------------------------------------------


class KernelPhase(StrEnum):
    """Lifecycle phases of the system kernel."""

    COLD = "COLD"
    BOOTING = "BOOTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class KernelSnapshot:
    """Immutable projection of the entire system state.

    This is the ONLY object any service or UI widget should read.
    No local caches, no dashboard-local state, no adapter-local truth.
    """

    version: int = 0
    ts_ns: int = 0
    phase: KernelPhase = KernelPhase.COLD

    # Canonical system mode (ONLY the kernel writes this)
    mode: SystemMode = field(default_factory=lambda: SystemMode(1))

    # Canonical belief state (ONLY the kernel writes this)
    belief: BeliefState = field(
        default_factory=lambda: BeliefState(
            ts_ns=0,
            regime=Regime.UNKNOWN,
            regime_confidence=0.0,
            consensus_side=Side.HOLD,
            signal_count=0,
            avg_confidence=0.0,
        )
    )

    # Service health
    services: tuple[ServiceHealth, ...] = ()

    # Execution state
    live_execution_blocked: bool = True
    freeze_active: bool = False


@dataclass(frozen=True, slots=True)
class ServiceHealth:
    """Health report from a registered service."""

    name: str
    healthy: bool
    detail: str = ""


# ---------------------------------------------------------------------------
# Service Protocol
# ---------------------------------------------------------------------------


class KernelService(Protocol):
    """Protocol for services that register with the kernel.

    Every engine, adapter, and subsystem implements this protocol to
    participate in the kernel's event dispatch and health monitoring.
    """

    @property
    def name(self) -> str: ...

    def process(self, event: Event) -> Sequence[Event]:
        """Process an event and return any output events."""
        ...

    def check_health(self) -> ServiceHealth:
        """Report current health status."""
        ...


# ---------------------------------------------------------------------------
# Engine → KernelService adapter
# ---------------------------------------------------------------------------


class EngineServiceAdapter:
    """Adapts an existing Engine (check_self → HealthStatus) to KernelService.

    The six canonical engines (intelligence, execution, governance,
    system, learning, evolution) implement :class:`Engine` from
    ``core.contracts.engine`` with ``check_self() → HealthStatus``.
    This adapter bridges them to the :class:`KernelService` protocol
    expected by :class:`SystemKernel`.
    """

    __slots__ = ("_engine",)

    def __init__(self, engine: object) -> None:
        self._engine = engine

    @property
    def name(self) -> str:
        return getattr(self._engine, "name", type(self._engine).__name__)

    def process(self, event: Event) -> Sequence[Event]:
        proc = getattr(self._engine, "process", None)
        if proc is not None:
            result = proc(event)
            return list(result) if result else []
        return []

    def check_health(self) -> ServiceHealth:
        check = getattr(self._engine, "check_self", None)
        if check is None:
            return ServiceHealth(name=self.name, healthy=True, detail="no check_self")
        status = check()
        healthy = str(getattr(status, "state", "OK")) == "OK"
        detail = getattr(status, "detail", "")
        return ServiceHealth(name=self.name, healthy=healthy, detail=detail)


# ---------------------------------------------------------------------------
# SystemKernel
# ---------------------------------------------------------------------------


class SystemKernel:
    """The single canonical runtime state authority.

    Usage::

        kernel = SystemKernel()
        kernel.register_service(intelligence_engine)
        kernel.register_service(execution_engine)
        kernel.register_service(governance_engine)
        kernel.boot()

        # Every tick:
        snapshot = kernel.snapshot  # Read-only, thread-safe
        kernel.dispatch(event)     # Typed event to all services
        kernel.update_belief(...)  # Update canonical BeliefState

        # UI widgets:
        snapshot = kernel.project()  # Same as .snapshot
    """

    __slots__ = (
        "_snapshot",
        "_lock",
        "_services",
        "_listeners",
        "_tick_count",
    )

    def __init__(self) -> None:
        self._snapshot = KernelSnapshot()
        self._lock = threading.RLock()
        self._services: dict[str, KernelService] = {}
        self._listeners: list[Callable[[KernelSnapshot], None]] = []
        self._tick_count = 0

    # -- Read path (lock-free) ------------------------------------------

    @property
    def snapshot(self) -> KernelSnapshot:
        """Current immutable snapshot. Thread-safe, no lock needed."""
        return self._snapshot

    def project(self) -> KernelSnapshot:
        """Read-only projection for UI widgets.

        Identical to :attr:`snapshot` — exists as a named API so that
        dashboard code self-documents its data source::

            data = kernel.project()  # not some local mock
        """
        return self._snapshot

    # -- Service registration -------------------------------------------

    def register_service(self, service: KernelService) -> None:
        """Register a service with the kernel."""
        with self._lock:
            if self._snapshot.phase not in (KernelPhase.COLD, KernelPhase.BOOTING):
                raise RuntimeError(f"Cannot register service '{service.name}' after boot")
            self._services[service.name] = service
            _logger.info("Kernel: registered service %s", service.name)

    def on_snapshot_change(self, listener: Callable[[KernelSnapshot], None]) -> None:
        """Register a listener for snapshot changes (e.g. UI refresh)."""
        self._listeners.append(listener)

    # -- Write path (serialized) ----------------------------------------

    def boot(self) -> bool:
        """Boot the kernel. Returns True if all services are healthy."""
        with self._lock:
            self._snapshot = replace(self._snapshot, phase=KernelPhase.BOOTING)
            _logger.info("Kernel: booting with %d services", len(self._services))

            healths: list[ServiceHealth] = []
            all_healthy = True
            for svc in self._services.values():
                try:
                    h = svc.check_health()
                    healths.append(h)
                    if not h.healthy:
                        all_healthy = False
                        _logger.warning("Kernel: service %s unhealthy: %s", svc.name, h.detail)
                except Exception as exc:
                    all_healthy = False
                    healths.append(ServiceHealth(name=svc.name, healthy=False, detail=str(exc)))
                    _logger.exception("Kernel: service %s health check failed", svc.name)

            phase = KernelPhase.RUNNING if all_healthy else KernelPhase.DEGRADED
            self._snapshot = replace(
                self._snapshot,
                phase=phase,
                version=self._snapshot.version + 1,
                ts_ns=wall_ns(),
                services=tuple(healths),
            )
            _logger.info("Kernel: boot complete (phase=%s)", phase)
            self._notify()
            return all_healthy

    def dispatch(self, event: Event) -> list[Event]:
        """Dispatch a typed event to all registered services.

        Returns any output events produced by services.
        This is the ONLY event dispatch path in the system.
        """
        outputs: list[Event] = []
        for svc in self._services.values():
            try:
                result = svc.process(event)
                if result:
                    outputs.extend(result)
            except Exception:
                _logger.exception(
                    "Kernel: service %s failed processing %s",
                    svc.name,
                    type(event).__name__,
                )
        return outputs

    def transition_mode(self, new_mode: SystemMode, *, reason: str = "") -> bool:
        """Transition the canonical system mode.

        This is the ONLY path for mode changes. Returns True if
        the transition was accepted.
        """
        with self._lock:
            old = self._snapshot.mode
            if old == new_mode:
                return True

            eff = effect_for(new_mode)
            blocked = eff.executions_dispatch and self._snapshot.live_execution_blocked
            if blocked:
                _logger.warning(
                    "Kernel: mode transition %s→%s BLOCKED (live execution blocked)",
                    old,
                    new_mode,
                )
                return False

            self._snapshot = replace(
                self._snapshot,
                mode=new_mode,
                version=self._snapshot.version + 1,
                ts_ns=wall_ns(),
            )
            _logger.info(
                "Kernel: mode transition %s→%s (reason=%s)",
                old,
                new_mode,
                reason or "unspecified",
            )
            self._notify()
            return True

    def update_belief(self, belief: BeliefState) -> None:
        """Update the canonical BeliefState.

        This is the ONLY path for BeliefState changes.
        """
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                belief=belief,
                version=self._snapshot.version + 1,
                ts_ns=wall_ns(),
            )
            self._notify()

    def set_freeze(self, active: bool, *, reason: str = "") -> None:
        """Set the global freeze state."""
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                freeze_active=active,
                version=self._snapshot.version + 1,
                ts_ns=wall_ns(),
            )
            _logger.info("Kernel: freeze=%s (reason=%s)", active, reason or "unspecified")
            self._notify()

    def set_execution_blocked(self, blocked: bool) -> None:
        """Set whether live execution is blocked."""
        with self._lock:
            if self._snapshot.live_execution_blocked == blocked:
                return
            self._snapshot = replace(
                self._snapshot,
                live_execution_blocked=blocked,
                version=self._snapshot.version + 1,
                ts_ns=wall_ns(),
            )
            _logger.info("Kernel: live_execution_blocked=%s", blocked)
            self._notify()

    def halt(self, *, reason: str = "") -> None:
        """Halt the kernel."""
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                phase=KernelPhase.HALTED,
                version=self._snapshot.version + 1,
                ts_ns=wall_ns(),
            )
            _logger.info("Kernel: HALTED (reason=%s)", reason or "unspecified")
            self._notify()

    # -- Internal -------------------------------------------------------

    def _notify(self) -> None:
        snap = self._snapshot
        for listener in self._listeners:
            try:
                listener(snap)
            except Exception:
                _logger.exception("Kernel: snapshot listener failed")
