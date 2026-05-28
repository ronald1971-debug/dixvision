"""Event Loop — main execution loop tying all fabric stages (CONVERGENCE PILLAR 2).

This is the top-level orchestrator that:
1. Starts the ingestion bus
2. Feeds ticks through the decision pipeline
3. Routes intents through the execution router
4. Reconciles fills
5. Periodically computes risk snapshots

The loop is async and runs until stopped. Each iteration is a
"logical tick" with a consistent ts_ns.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto

from runtime.authority import RuntimeAuthorityStore
from runtime.fabric.decision_pipeline import DecisionPipeline
from runtime.fabric.execution_router import ExecutionRouter, RouteDecision
from runtime.fabric.fill_reconciler import FillReconciler
from runtime.fabric.ingestion_bus import IngestionBus
from runtime.fabric.risk_snapshotter import RiskSnapshotter


class LoopState(StrEnum):
    """Fabric event loop state."""

    IDLE = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    ERROR = auto()


@dataclass(frozen=True, slots=True)
class FabricMetrics:
    """Aggregate metrics for the entire fabric."""

    loop_iterations: int = 0
    ticks_ingested: int = 0
    intents_created: int = 0
    intents_executed: int = 0
    intents_queued: int = 0
    intents_blocked: int = 0
    fills_reconciled: int = 0
    errors: int = 0


class ExecutionFabric:
    """Main event loop orchestrating all fabric stages.

    Usage:
        store = RuntimeAuthorityStore()
        fabric = ExecutionFabric(store=store)
        await fabric.run()  # Blocks until stopped
    """

    def __init__(
        self,
        *,
        store: RuntimeAuthorityStore,
        risk_budget_usd: float = 10000.0,
    ) -> None:
        self._store = store
        self._state = LoopState.IDLE
        self._metrics = FabricMetrics()

        # Issue writer tokens for fabric components
        fabric_token = store.issue_writer_token("execution_fabric")

        # Initialize fabric stages
        self._ingestion = IngestionBus(store=store, writer_token=fabric_token)
        self._decision = DecisionPipeline(store=store)
        self._router = ExecutionRouter(store=store)
        self._reconciler = FillReconciler(store=store, writer_token=fabric_token)
        self._risk = RiskSnapshotter(
            store=store,
            writer_token=fabric_token,
            risk_budget_usd=risk_budget_usd,
        )

    @property
    def state(self) -> LoopState:
        return self._state

    @property
    def metrics(self) -> FabricMetrics:
        return self._metrics

    @property
    def ingestion(self) -> IngestionBus:
        return self._ingestion

    @property
    def reconciler(self) -> FillReconciler:
        return self._reconciler

    async def run(self) -> None:
        """Run the execution fabric event loop.

        Processes ticks from ingestion → decision → routing.
        Runs until stop() is called.
        """
        self._state = LoopState.RUNNING

        try:
            async for tick in self._ingestion.consume():
                if self._state != LoopState.RUNNING:
                    break

                # Decision pipeline
                intent = self._decision.process_tick(tick)

                iterations = self._metrics.loop_iterations + 1
                ticks = self._metrics.ticks_ingested + 1

                if intent is None:
                    self._metrics = FabricMetrics(
                        loop_iterations=iterations,
                        ticks_ingested=ticks,
                        intents_created=self._metrics.intents_created,
                        intents_executed=self._metrics.intents_executed,
                        intents_queued=self._metrics.intents_queued,
                        intents_blocked=self._metrics.intents_blocked,
                        fills_reconciled=self._metrics.fills_reconciled,
                        errors=self._metrics.errors,
                    )
                    continue

                # Route intent
                result = self._router.route(intent)

                intents_created = self._metrics.intents_created + 1
                executed = self._metrics.intents_executed
                queued = self._metrics.intents_queued
                blocked = self._metrics.intents_blocked

                if result.decision == RouteDecision.EXECUTE:
                    executed += 1
                elif result.decision == RouteDecision.SEMI_AUTO_QUEUE:
                    queued += 1
                else:
                    blocked += 1

                self._metrics = FabricMetrics(
                    loop_iterations=iterations,
                    ticks_ingested=ticks,
                    intents_created=intents_created,
                    intents_executed=executed,
                    intents_queued=queued,
                    intents_blocked=blocked,
                    fills_reconciled=self._metrics.fills_reconciled,
                    errors=self._metrics.errors,
                )

        except Exception:
            self._state = LoopState.ERROR
            self._metrics = FabricMetrics(
                loop_iterations=self._metrics.loop_iterations,
                ticks_ingested=self._metrics.ticks_ingested,
                intents_created=self._metrics.intents_created,
                intents_executed=self._metrics.intents_executed,
                intents_queued=self._metrics.intents_queued,
                intents_blocked=self._metrics.intents_blocked,
                fills_reconciled=self._metrics.fills_reconciled,
                errors=self._metrics.errors + 1,
            )
            raise
        finally:
            if self._state != LoopState.ERROR:
                self._state = LoopState.STOPPED

    def stop(self) -> None:
        """Signal the fabric to stop processing."""
        self._state = LoopState.STOPPING
        self._ingestion.stop()

    def compute_risk(self, ts_ns: int) -> None:
        """Trigger a risk snapshot computation."""
        self._risk.compute(ts_ns)
