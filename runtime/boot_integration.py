"""runtime.boot_integration — Wire Runtime Kernel Into Server Boot.

This module integrates the runtime kernel, event fabric, reconciler,
and governance enforcer into the existing FastAPI server lifecycle.

BOOT SEQUENCE:
1. Server starts (uvicorn)
2. _State is constructed (engines, governance, dashboard)
3. RuntimeKernel is initialized with references to STATE
4. CognitionDaemon started (drives CognitiveSpine — all cognitive subsystems)
5. Kernel starts background tick loop (execution fabric heartbeat)
6. Each tick: reconcile → replay → lifecycle → health

Cognitive subsystems (INDIRA, DYON, memory, trader intelligence, telemetry)
are driven exclusively by CognitionDaemon → CognitiveSpine.  The execution
tick loop handles ONLY execution-fabric concerns.

SHUTDOWN:
1. Kernel receives stop signal
2. CognitionDaemon stopped (gracefully cancels spine loop)
3. Completes current tick
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
        "_propagator",
        "_kernel",
        "_cognition_daemon",
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
        self._propagator: Any = None
        self._kernel: Any = None
        self._cognition_daemon: Any = None

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
        from runtime.event_fabric import get_event_fabric
        from runtime.execution_lifecycle import get_lifecycle_manager
        from runtime.fault_handler import FaultHandler
        from runtime.governance.runtime_enforcer import RuntimeGovernanceEnforcer
        from runtime.operational_readiness import OperationalReadinessValidator
        from runtime.reconciliation import StateReconciler
        from runtime.replay_validator import ReplayValidator

        # Initialize components — use the process-level singleton so all
        # publishers (cognitive_governance, system events, etc.) and
        # subscribers share ONE fabric instance.
        self._fabric = get_event_fabric()
        self._enforcer = RuntimeGovernanceEnforcer(store=_get_authority_store(state))
        self._reconciler = StateReconciler(store=_get_authority_store(state))
        self._replay = ReplayValidator()
        self._readiness = OperationalReadinessValidator(store=_get_authority_store(state))
        self._fault_handler = FaultHandler()
        self._lifecycle_mgr = get_lifecycle_manager()

        # Register subsystems with reconciler
        self._register_subsystems(state)

        # Wire the ModePropagator to the GOVERNANCE channel so critical
        # cognitive violations drive synchronous mode transitions through
        # the kernel (canonical mode authority).
        from core.contracts.governance import SystemMode  # noqa: PLC0415
        from runtime.event_fabric import EventAck, EventChannel  # noqa: PLC0415
        from runtime.governance.mode_propagator import ModePropagator  # noqa: PLC0415

        # Sync propagator initial mode with kernel's current mode (if available).
        _initial_mode = "PAPER"
        if hasattr(state, "system_kernel"):
            _initial_mode = state.system_kernel.snapshot.mode.name
        self._propagator = ModePropagator(initial_mode=_initial_mode)
        self._kernel = getattr(state, "system_kernel", None)

        def _on_governance_event(event: Any) -> Any:
            """Route critical cognitive violations through the kernel FSM.

            SystemKernel is the canonical mode writer.  We never call
            propagator.propagate() directly here — the snapshot listener
            below takes care of broadcasting after the kernel commits.
            """
            if event.event_type in ("COGOV_CRITICAL_VIOLATION",):
                try:
                    if self._kernel is not None:
                        self._kernel.transition_mode(
                            SystemMode.SAFE,
                            reason="cognitive_governance",
                        )
                    else:
                        # Kernel not available yet — fall back to direct propagation.
                        self._propagator.propagate(
                            "SAFE",
                            triggered_by="cognitive_governance",
                        )
                except Exception:
                    pass
            return EventAck(
                event_sequence=event.sequence,
                subscriber_id="runtime_bootstrap",
                accepted=True,
            )

        self._fabric.subscribe(EventChannel.GOVERNANCE, "runtime_bootstrap", _on_governance_event)
        logger.info("ModePropagator subscribed to EventFabric.GOVERNANCE channel")

        # Step 10 — bind the kernel-backed authority shim so writes
        # to the legacy RuntimeAuthorityStore flow through SystemKernel.
        if hasattr(state, "system_kernel"):
            authority_store = _get_authority_store(state)
            if hasattr(authority_store, "bind_kernel"):
                authority_store.bind_kernel(state.system_kernel)
                logger.info("RuntimeAuthorityStore bound to SystemKernel (Step 10)")

        # Governance alignment — register a kernel snapshot listener that
        # keeps ModePropagator in sync and publishes MODE_TRANSITION to the
        # AUDIT channel whenever the canonical mode changes.
        if self._kernel is not None:
            _last_mode: list[str] = [self._kernel.snapshot.mode.name]

            def _on_kernel_snapshot(snap: Any) -> None:
                new_name = snap.mode.name
                if new_name == _last_mode[0]:
                    return
                old_name = _last_mode[0]
                _last_mode[0] = new_name
                # Broadcast to registered subsystems via propagator.
                try:
                    self._propagator.propagate(new_name, triggered_by="kernel_fsm")
                except Exception:
                    pass
                # Publish an audit event so the mode transition is observable.
                try:
                    self._fabric.publish(
                        EventChannel.AUDIT,
                        "MODE_TRANSITION",
                        {"old_mode": old_name, "new_mode": new_name},
                        source="runtime_bootstrap",
                    )
                except Exception:
                    pass

            self._kernel.on_snapshot_change(_on_kernel_snapshot)
            logger.info("Kernel snapshot listener registered for governance alignment")

        # Tier 1–2 completion (contracts, services, plugins, evolution, learning, memory)
        try:
            from runtime.tier_wiring import complete_tier_runtime

            report = complete_tier_runtime(kernel=getattr(state, "system_kernel", None), state=state)
            logger.info(
                "Tier wiring: T0=%s T1=%s T2=%s (services=%d plugins=%d)",
                report.tier0_complete,
                report.tier1_complete,
                report.tier2_complete,
                report.services_registered,
                report.plugins_loaded,
            )
        except Exception as exc:
            logger.debug("Tier wiring skipped: %s", exc)

        # Run initial readiness check
        report = self._readiness.assess()
        logger.info(
            "Initial readiness: %s (%d/%d checks)",
            report.level,
            report.passed_checks,
            report.total_checks,
        )

        # OPERATOR-AUTHORITY — start AutonomousResearchRuntime daemon so INDIRA
        # researches backtesting platforms and market intelligence continuously.
        try:
            from intelligence_engine.research.autonomous_research_runtime import (
                get_research_runtime,
            )
            from intelligence_engine.research.browser_research_service import (
                ResearchTaskType,
            )
            from intelligence_engine.research.autonomous_research_runtime import ResearchTopic
            import time as _time
            _research_rt = get_research_runtime()
            _research_rt.start()
            # Seed with initial discovery topics so the daemon has work on boot.
            _now_ns = int(_time.time_ns())
            for _topic in (
                "backtesting platform API free algorithmic trading",
                "crypto trading bot autonomous backtesting 2024",
                "market microstructure research papers 2024",
            ):
                _research_rt.enqueue(ResearchTopic(
                    topic=_topic,
                    task_type=ResearchTaskType.MARKET_ANALYSIS,
                    priority=6,
                    ts_ns=_now_ns,
                ))
            logger.info("Cognitive: AutonomousResearchRuntime started (LIVE authority)")
        except Exception as _exc:
            logger.warning("Cognitive: AutonomousResearchRuntime unavailable — %s", _exc)

        # Start CognitionDaemon — THE authoritative cognitive loop.
        # Activates CognitiveSpine which sequences: cogov → memory → trader → INDIRA → DYON.
        # Runs independently of execution fabric state (Cognitive Integrity is P0).
        try:
            from runtime.cognition_daemon import get_cognition_daemon
            self._cognition_daemon = get_cognition_daemon()
            self._cognition_daemon.start()
            logger.info("CognitionDaemon started (unified cognitive spine — 2s cadence)")
        except Exception as _exc:
            logger.warning("CognitionDaemon unavailable — %s", _exc)

        # Start execution-fabric tick loop (reconcile / replay / lifecycle / health only)
        self._running = True
        self._kernel_task = asyncio.create_task(self._tick_loop())
        logger.info("Runtime kernel started (tick_interval=%.0fms)", self._tick_interval_ms)

    async def _tick_loop(self) -> None:
        """Execution-fabric heartbeat — reconciliation, replay, health only.

        Cognitive subsystems (INDIRA, DYON, memory, telemetry) are driven
        exclusively by CognitionDaemon → CognitiveSpine.
        """
        tick_count = 0
        interval_s = self._tick_interval_ms / 1000.0

        while self._running:
            try:
                tick_start = time_source.now_ns()

                # Phase 1: Reconciliation (every 10 ticks)
                if tick_count % 10 == 0 and self._reconciler:
                    await asyncio.to_thread(self._reconciler.tick)

                # Phase 2: Replay validation (handled internally by validator)
                if self._replay:
                    await asyncio.to_thread(self._replay.tick)

                # Phase 3: Expire stale intents
                if self._lifecycle_mgr:
                    await asyncio.to_thread(self._lifecycle_mgr.expire_stale)

                # Phase 4: Health check (every 50 ticks)
                if tick_count % 50 == 0 and self._readiness:
                    await asyncio.to_thread(self._readiness.assess)

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
        """Gracefully stop the runtime kernel and cognition daemon."""
        self._running = False
        if self._cognition_daemon is not None:
            try:
                await self._cognition_daemon.stop()
            except Exception:
                pass
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

    @property
    def propagator(self) -> Any:
        return self._propagator

    @property
    def kernel(self) -> Any:
        return self._kernel

    @property
    def cognition_daemon(self) -> Any:
        return self._cognition_daemon


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
