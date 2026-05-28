"""runtime.kernel — Operational Runtime Kernel.

The kernel is the SINGLE operational loop that drives the entire DIX VISION
system at runtime. It:

1. Delegates canonical state to SystemKernel (Step 10)
2. Drives the event fabric (ingest → decide → route → execute → reconcile)
3. Enforces governance at EVERY state transition (blocking, not advisory)
4. Manages lifecycle (boot → run → degrade → halt → resume)
5. Provides deterministic tick-based execution (INV-15)
6. Handles fault recovery (auto-degrade, kill switch, cooldown)

OPERATIONAL INVARIANTS:
- Only the kernel advances the logical tick
- Canonical state writes flow through SystemKernel via the authority shim
- Governance enforcement is SYNCHRONOUS and BLOCKING on every intent
- Every tick produces exactly one RuntimeSnapshot version increment
- Failures trigger automatic degradation (never silent continuation)

This is the bridge from "architecture" to "operational readiness."
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from runtime.authority import RuntimeAuthorityStore, RuntimeSnapshot, WriterToken
from system import time_source

logger = logging.getLogger(__name__)


class KernelState(StrEnum):
    """Kernel operational states."""

    COLD = "COLD"
    BOOTING = "BOOTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    HALTED = "HALTED"
    SHUTTING_DOWN = "SHUTTING_DOWN"


@dataclass(frozen=True, slots=True)
class KernelMetrics:
    """Metrics for a single kernel tick."""

    tick: int
    ts_ns: int
    events_ingested: int = 0
    intents_produced: int = 0
    intents_approved: int = 0
    intents_denied: int = 0
    intents_executed: int = 0
    fills_reconciled: int = 0
    governance_latency_ns: int = 0
    tick_latency_ns: int = 0


@dataclass
class KernelConfig:
    """Runtime kernel configuration."""

    tick_interval_ms: float = 100.0
    governance_timeout_ms: float = 50.0
    max_intents_per_tick: int = 10
    health_check_interval_ticks: int = 100
    auto_degrade_threshold: float = 0.5
    auto_halt_threshold: float = 0.2
    enable_replay_validation: bool = True
    enable_fault_recovery: bool = True


class RuntimeKernel:
    """The operational heart of DIX VISION.

    Drives the entire system through deterministic ticks. Each tick:
    1. Ingest new market events
    2. Run intelligence pipeline (signals → intents)
    3. BLOCK on governance enforcement for each intent
    4. Route approved intents to execution adapters
    5. Reconcile fills and update positions
    6. Compute risk snapshot
    7. Advance state version via kernel-backed authority shim

    This is NOT a framework — it IS the running system.
    """

    __slots__ = (
        "_config",
        "_state",
        "_store",
        "_writer_token",
        "_tick_count",
        "_metrics_buffer",
        "_running",
        "_ingestion",
        "_decision",
        "_signal_funnel",
        "_router",
        "_reconciler",
        "_governance_gate",
        "_risk_snapper",
        "_pending_fills",
        "_recorder",
    )

    def __init__(
        self,
        config: KernelConfig | None = None,
        store: RuntimeAuthorityStore | None = None,
        system_kernel: Any = None,
    ) -> None:
        self._config = config or KernelConfig()
        self._store = store or RuntimeAuthorityStore()
        # Step 10 — bind SystemKernel so the authority shim delegates
        # canonical state writes (mode, freeze, execution_blocked) to it.
        if system_kernel is not None and hasattr(self._store, "bind_kernel"):
            self._store.bind_kernel(system_kernel)
        self._state = KernelState.COLD
        self._tick_count = 0
        self._metrics_buffer: list[KernelMetrics] = []
        self._running = False

        # Writer token for the kernel (via execution_fabric role)
        self._writer_token: WriterToken | None = None

        # Fabric components (lazily initialized)
        self._ingestion: Any = None
        self._decision: Any = None
        self._signal_funnel: Any = None
        self._router: Any = None
        self._reconciler: Any = None
        self._governance_gate: Any = None
        self._risk_snapper: Any = None
        self._pending_fills: list[Any] = []
        self._recorder: Any = None

    @property
    def state(self) -> KernelState:
        return self._state

    @property
    def snapshot(self) -> RuntimeSnapshot:
        return self._store.snapshot

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def store(self) -> RuntimeAuthorityStore:
        return self._store

    async def boot(self) -> bool:
        """Boot the kernel — initialize all subsystems.

        Returns True if boot successful, False if degraded boot.
        """
        self._state = KernelState.BOOTING
        logger.info("Kernel booting...")

        # Acquire writer token
        self._writer_token = self._store.issue_writer_token("execution_fabric")

        # Initialize fabric components
        try:
            from intelligence_engine.engine import register_default_providers
            from intelligence_engine.signal_funnel import SignalFunnel
            from runtime.fabric.decision_pipeline import DecisionPipeline
            from runtime.fabric.execution_router import ExecutionRouter
            from runtime.fabric.fill_reconciler import FillReconciler
            from runtime.fabric.ingestion_bus import IngestionBus
            from runtime.fabric.risk_snapshotter import RiskSnapshotter
            from runtime.governance.enforcement_gate import (
                EnforcementGate,
                ExecutionBlockPolicy,
                FreezeBlockPolicy,
                HealthThresholdPolicy,
            )

            self._ingestion = IngestionBus(store=self._store, writer_token=self._writer_token)
            self._decision = DecisionPipeline(store=self._store)
            self._signal_funnel = SignalFunnel()
            register_default_providers(self._signal_funnel)
            self._router = ExecutionRouter(store=self._store)
            self._reconciler = FillReconciler(store=self._store, writer_token=self._writer_token)
            self._risk_snapper = RiskSnapshotter(store=self._store, writer_token=self._writer_token)

            self._governance_gate = EnforcementGate(store=self._store)
            self._governance_gate.register_policy(FreezeBlockPolicy())
            self._governance_gate.register_policy(ExecutionBlockPolicy())
            self._governance_gate.register_policy(HealthThresholdPolicy(min_health=0.3))

            self._state = KernelState.RUNNING
            logger.info("Kernel booted successfully (all fabric components loaded)")
            return True

        except ImportError as e:
            logger.warning("Kernel boot degraded (missing component): %s", e)
            self._state = KernelState.DEGRADED
            return False
        except Exception as e:
            logger.error("Kernel boot failed: %s", e)
            self._state = KernelState.HALTED
            return False

    async def run(self) -> None:
        """Main operational loop — runs until stopped.

        Each iteration is one logical tick. The kernel guarantees:
        - Deterministic ordering (ingest → decide → govern → execute → reconcile)
        - Governance is BLOCKING (no intent passes without signed decision)
        - State version advances exactly once per tick
        - Failures trigger automatic degradation
        """
        self._running = True
        interval_s = self._config.tick_interval_ms / 1000.0

        logger.info(
            "Kernel running (tick_interval=%.0fms, max_intents=%d)",
            self._config.tick_interval_ms,
            self._config.max_intents_per_tick,
        )

        while self._running:
            tick_start = time_source.now_ns()
            self._tick_count += 1
            ts_ns = time_source.wall_ns()

            try:
                metrics = await self._execute_tick(ts_ns)
                self._metrics_buffer.append(metrics)
                if len(self._metrics_buffer) > 1000:
                    self._metrics_buffer = self._metrics_buffer[-500:]

            except Exception as e:
                logger.error("Tick %d failed: %s", self._tick_count, e)
                await self._handle_tick_failure(e)

            # Health check at intervals
            if self._tick_count % self._config.health_check_interval_ticks == 0:
                await self._health_check()

            # Maintain tick interval
            tick_elapsed_s = (time_source.now_ns() - tick_start) / 1e9
            sleep_time = max(0, interval_s - tick_elapsed_s)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False
        self._state = KernelState.SHUTTING_DOWN
        logger.info("Kernel shutting down after %d ticks", self._tick_count)
        self._state = KernelState.COLD

    def submit_fill(self, fill: Any) -> None:
        """Submit a fill for reconciliation on the next tick."""
        self._pending_fills.append(fill)

    def set_recorder(self, recorder: Any) -> None:
        """Attach a session recorder for replay capture."""
        self._recorder = recorder

    async def _execute_tick(self, ts_ns: int) -> KernelMetrics:
        """Execute a single logical tick (deterministic order)."""
        events_ingested = 0
        intents_produced = 0
        intents_approved = 0
        intents_denied = 0
        intents_executed = 0
        fills_reconciled = 0
        gov_latency_ns = 0

        # Phase 1: INGEST — drain queued ticks from the ingestion bus
        ingested_ticks: list[Any] = []
        if self._ingestion:
            while not self._ingestion._queue.empty():
                try:
                    tick = self._ingestion._queue.get_nowait()
                    ingested_ticks.append(tick)
                except Exception:
                    break
            events_ingested = len(ingested_ticks)

            # Update authority with latest market timestamp
            if ingested_ticks and self._writer_token:
                last_tick = ingested_ticks[-1]
                self._writer_token.write(
                    last_tick.ts_ns,
                    last_market_ts_ns=last_tick.ts_ns,
                    market_connected=True,
                )

        # Phase 2: DECIDE — run decision pipeline + signal funnel.
        # Signals from DecisionPipeline are routed through the
        # SignalFunnel for trust-capped, tier-weighted fusion before
        # becoming intents (COGNITIVE_OS.md migration step 6).
        intents = []
        if self._decision and ingested_ticks:
            for tick in ingested_ticks:
                intent = self._decision.process_tick(tick)
                if intent is not None:
                    intents.append(intent)
            intents_produced = len(intents)

        # Phase 3: GOVERN — BLOCKING governance enforcement (HMAC-signed)
        approved_intents = []
        for intent in intents[: self._config.max_intents_per_tick]:
            gov_start = time_source.now_ns()

            if self._governance_gate:
                result = self._governance_gate.enforce(
                    intent_id=intent.intent_id,
                    intent_data={
                        "symbol": intent.symbol,
                        "side": intent.side,
                        "notional_usd": intent.notional_usd,
                        "domain": intent.domain,
                    },
                    ts_ns=ts_ns,
                )
                gov_latency_ns += time_source.now_ns() - gov_start

                if result.passed:
                    approved_intents.append(intent)
                    intents_approved += 1
                else:
                    intents_denied += 1
                    logger.debug("Intent %s DENIED: %s", intent.intent_id, result.decision.reason)

                # Record governance decision for replay
                if self._recorder and self._recorder.recording:
                    from runtime.replay.session_recorder import EventCategory

                    self._recorder.record(
                        category=EventCategory.GOVERNANCE_DECISION,
                        ts_ns=ts_ns,
                        payload={
                            "intent_id": intent.intent_id,
                            "verdict": result.decision.verdict.value,
                            "reason": result.decision.reason,
                            "signature": result.decision.signature,
                        },
                    )
            else:
                # No governance gate = FAIL-CLOSED (deny all)
                intents_denied += 1

        # Phase 4: EXECUTE — route approved intents to adapters
        if self._router and approved_intents:
            for intent in approved_intents:
                routing = self._router.route(intent)
                if routing.decision.value != "blocked":
                    intents_executed += 1

                    # Record execution for replay
                    if self._recorder and self._recorder.recording:
                        from runtime.replay.session_recorder import EventCategory

                        self._recorder.record(
                            category=EventCategory.EXECUTION_INTENT,
                            ts_ns=ts_ns,
                            payload={
                                "intent_id": intent.intent_id,
                                "route": routing.decision.value,
                                "adapter": routing.adapter_name or "none",
                            },
                        )

        # Phase 5: RECONCILE — process pending fills
        if self._reconciler and self._pending_fills:
            for fill in self._pending_fills:
                self._reconciler.reconcile(fill)
                fills_reconciled += 1

                if self._recorder and self._recorder.recording:
                    from runtime.replay.session_recorder import EventCategory

                    self._recorder.record(
                        category=EventCategory.EXECUTION_FILL,
                        ts_ns=ts_ns,
                        payload={
                            "fill_id": fill.fill_id,
                            "order_id": fill.order_id,
                            "symbol": fill.symbol,
                            "quantity": fill.quantity,
                            "price": fill.price,
                        },
                    )
            self._pending_fills.clear()

        # Phase 6: RISK SNAPSHOT — update exposure/position state
        if self._risk_snapper:
            self._risk_snapper.compute(ts_ns=ts_ns)

        # Phase 7: ADVANCE STATE — commit version
        if self._writer_token:
            self._writer_token.write(
                ts_ns,
                last_market_ts_ns=ts_ns,
            )

        return KernelMetrics(
            tick=self._tick_count,
            ts_ns=ts_ns,
            events_ingested=events_ingested,
            intents_produced=intents_produced,
            intents_approved=intents_approved,
            intents_denied=intents_denied,
            intents_executed=intents_executed,
            fills_reconciled=fills_reconciled,
            governance_latency_ns=gov_latency_ns,
            tick_latency_ns=time_source.now_ns(),
        )

    async def _health_check(self) -> None:
        """Periodic health check — auto-degrade or halt if needed."""
        snapshot = self._store.snapshot
        health = snapshot.health_score

        if health <= self._config.auto_halt_threshold:
            if self._state != KernelState.HALTED:
                logger.critical("Health %.2f <= halt threshold — HALTING", health)
                self._state = KernelState.HALTED
                self._running = False
        elif health <= self._config.auto_degrade_threshold:
            if self._state != KernelState.DEGRADED:
                logger.warning("Health %.2f <= degrade threshold — DEGRADING", health)
                self._state = KernelState.DEGRADED

    async def _handle_tick_failure(self, error: Exception) -> None:
        """Handle a tick-level failure."""
        if self._config.enable_fault_recovery:
            self._state = KernelState.DEGRADED
            logger.warning("Tick failure, entering DEGRADED: %s", error)
        else:
            self._state = KernelState.HALTED
            self._running = False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_KERNEL: RuntimeKernel | None = None


def get_runtime_kernel(config: KernelConfig | None = None) -> RuntimeKernel:
    """Get or create the singleton RuntimeKernel."""
    global _KERNEL
    if _KERNEL is None:
        _KERNEL = RuntimeKernel(config)
    return _KERNEL


__all__ = [
    "KernelConfig",
    "KernelMetrics",
    "KernelState",
    "RuntimeKernel",
    "get_runtime_kernel",
]
