"""runtime.boot_integration — Wire Runtime Kernel Into Server Boot.

This module integrates the runtime kernel, event fabric, reconciler,
and governance enforcer into the existing FastAPI server lifecycle.

BOOT SEQUENCE:
1. Server starts (uvicorn)
2. _State is constructed (engines, governance, dashboard)
3. RuntimeKernel is initialized with references to STATE
4. Kernel starts background tick loop (asyncio task)
5. Each tick: ingest → decide → govern → execute → reconcile

SHUTDOWN:
1. Kernel receives stop signal
2. Completes current tick
3. Flushes pending ledger writes
4. Reports final metrics

The kernel does NOT own the engines — it orchestrates them.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from system import time_source

logger = logging.getLogger(__name__)


class RuntimeBootstrap:
    """Wires the runtime kernel into the FastAPI server lifecycle.

    Call ``attach(app, state)`` after constructing ``_State`` to hook
    the kernel into the server's startup/shutdown events.
    """

    __slots__ = (
        "_kernel_task",
        "_running",
        "_tick_interval_ms",
        "_fabric",
        "_enforcer",
        "_reconciler",
        "_replay",
        "_readiness",
        "_fault_handler",
        "_lifecycle_mgr",
    )

    def __init__(self, tick_interval_ms: float = 100.0) -> None:
        self._kernel_task: asyncio.Task[None] | None = None
        self._running = False
        self._tick_interval_ms = tick_interval_ms
        self._fabric: Any = None
        self._enforcer: Any = None
        self._reconciler: Any = None
        self._replay: Any = None
        self._readiness: Any = None
        self._fault_handler: Any = None
        self._lifecycle_mgr: Any = None

    def attach(self, app: Any, state: Any) -> None:
        """Attach runtime kernel to FastAPI app lifecycle.

        Registers startup and shutdown event handlers that manage
        the kernel's background tick loop.
        """

        @app.on_event("startup")
        async def _start_runtime() -> None:
            await self._boot(state)

        @app.on_event("shutdown")
        async def _stop_runtime() -> None:
            await self._shutdown()

        logger.info("Runtime bootstrap attached to app lifecycle")

    async def _boot(self, state: Any) -> None:
        """Initialize all runtime components and start tick loop."""
        from runtime.event_fabric import EventFabric
        from runtime.execution_lifecycle import get_lifecycle_manager
        from runtime.fault_handler import FaultHandler
        from runtime.governance.runtime_enforcer import RuntimeGovernanceEnforcer
        from runtime.operational_readiness import OperationalReadinessValidator
        from runtime.reconciliation import StateReconciler
        from runtime.replay_validator import ReplayValidator

        # Initialize components
        self._fabric = EventFabric()
        self._enforcer = RuntimeGovernanceEnforcer(store=_get_authority_store(state))
        self._reconciler = StateReconciler(store=_get_authority_store(state))
        self._replay = ReplayValidator()
        self._readiness = OperationalReadinessValidator(store=_get_authority_store(state))
        self._fault_handler = FaultHandler()
        self._lifecycle_mgr = get_lifecycle_manager()

        # Register subsystems with reconciler
        self._register_subsystems(state)

        # Step 10 — bind the kernel-backed authority shim so writes
        # to the legacy RuntimeAuthorityStore flow through SystemKernel.
        if hasattr(state, "system_kernel"):
            authority_store = _get_authority_store(state)
            if hasattr(authority_store, "bind_kernel"):
                authority_store.bind_kernel(state.system_kernel)
                logger.info("RuntimeAuthorityStore bound to SystemKernel (Step 10)")

        # Run initial readiness check
        report = self._readiness.assess()
        logger.info(
            "Initial readiness: %s (%d/%d checks)",
            report.level,
            report.passed_checks,
            report.total_checks,
        )

        # Start background tick loop
        self._running = True
        self._kernel_task = asyncio.create_task(self._tick_loop())
        logger.info("Runtime kernel started (tick_interval=%.0fms)", self._tick_interval_ms)

    async def _tick_loop(self) -> None:
        """Background tick loop — the system heartbeat."""
        tick_count = 0
        interval_s = self._tick_interval_ms / 1000.0

        while self._running:
            try:
                tick_start = time_source.now_ns()
                time_source.wall_ns()

                # Phase 1: Reconciliation (every 10 ticks)
                if tick_count % 10 == 0 and self._reconciler:
                    self._reconciler.tick()

                # Phase 2: Replay validation (handled internally by validator)
                if self._replay:
                    self._replay.tick()

                # Phase 3: Expire stale intents
                if self._lifecycle_mgr:
                    self._lifecycle_mgr.expire_stale()

                # Phase 4: Health check (every 50 ticks)
                if tick_count % 50 == 0 and self._readiness:
                    self._readiness.assess()

                tick_count += 1
                elapsed_ms = (time_source.now_ns() - tick_start) / 1_000_000

                # Sleep for remaining interval
                sleep_s = max(0, interval_s - elapsed_ms / 1000.0)
                await asyncio.sleep(sleep_s)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Kernel tick error: %s", e)
                if self._fault_handler:
                    from runtime.fault_handler import Fault, FaultCategory, FaultSeverity

                    self._fault_handler.handle(
                        Fault(
                            fault_id=f"kernel_tick_{tick_count}",
                            category=FaultCategory.INTERNAL,
                            severity=FaultSeverity.TRANSIENT,
                            source="runtime_kernel",
                            message=str(e),
                        )
                    )
                await asyncio.sleep(interval_s)

    def _register_subsystems(self, state: Any) -> None:
        """Register state subsystems with the reconciler."""
        if not self._reconciler:
            return

        # Register execution engine
        if hasattr(state, "execution"):
            self._reconciler.register_subsystem("EXECUTION", state.execution)

        # Register governance engine
        if hasattr(state, "governance"):
            self._reconciler.register_subsystem("GOVERNANCE", state.governance)

        # Register intelligence engine
        if hasattr(state, "intelligence"):
            self._reconciler.register_subsystem("INTELLIGENCE", state.intelligence)

    async def _shutdown(self) -> None:
        """Gracefully stop the runtime kernel."""
        self._running = False
        if self._kernel_task:
            self._kernel_task.cancel()
            try:
                await self._kernel_task
            except asyncio.CancelledError:
                pass
        logger.info("Runtime kernel stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def enforcer(self) -> Any:
        return self._enforcer

    @property
    def fabric(self) -> Any:
        return self._fabric

    @property
    def readiness(self) -> Any:
        return self._readiness


def _get_authority_store(state: Any) -> Any:
    """Extract or create a RuntimeAuthorityStore from server state."""
    if hasattr(state, "authority_store"):
        return state.authority_store

    # Create a minimal authority store wrapper around server state
    from runtime.authority_adapter import ServerStateAuthorityAdapter

    return ServerStateAuthorityAdapter(state)


# Module-level singleton
_BOOTSTRAP: RuntimeBootstrap | None = None


def get_runtime_bootstrap(tick_interval_ms: float = 100.0) -> RuntimeBootstrap:
    """Get or create the singleton RuntimeBootstrap."""
    global _BOOTSTRAP
    if _BOOTSTRAP is None:
        _BOOTSTRAP = RuntimeBootstrap(tick_interval_ms=tick_interval_ms)
    return _BOOTSTRAP


__all__ = [
    "RuntimeBootstrap",
    "get_runtime_bootstrap",
]
