"""Execution Router — intent → route decision → adapter (CONVERGENCE PILLAR 2).

Routes execution intents based on the RuntimeAuthority state:
- BLOCKED → no execution (learning phase)
- PAPER → paper broker
- SEMI_AUTO → approval queue or auto-fire
- EXECUTE → live adapter

Integrates with:
- execution_engine/execution_gate.py (route_with_authority)
- execution_engine/semi_auto/ (threshold gate, approval queue)
- RuntimeAuthority (reads current state)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto

from runtime.authority import RuntimeAuthorityStore
from runtime.fabric.decision_pipeline import ExecutionIntent


class RouteDecision(StrEnum):
    """Where an intent gets routed."""

    BLOCKED = auto()
    PAPER = auto()
    SEMI_AUTO_QUEUE = auto()
    EXECUTE = auto()


@dataclass(frozen=True, slots=True)
class RoutingResult:
    """Result of routing an intent."""

    intent: ExecutionIntent
    decision: RouteDecision
    reason: str
    adapter_name: str | None = None


@dataclass(frozen=True, slots=True)
class RouterMetrics:
    """Routing telemetry."""

    intents_routed: int = 0
    blocked_count: int = 0
    paper_count: int = 0
    queued_count: int = 0
    executed_count: int = 0


class ExecutionRouter:
    """Routes intents based on RuntimeAuthority state.

    Reads the current snapshot to determine routing:
    1. live_execution_blocked → BLOCKED or PAPER (if practice ON)
    2. trading_mode MANUAL → BLOCKED
    3. trading_mode SEMI_AUTO → queue or auto-fire (based on exit/threshold)
    4. trading_mode FULL_AUTO → EXECUTE
    """

    def __init__(self, *, store: RuntimeAuthorityStore) -> None:
        self._store = store
        self._metrics = RouterMetrics()

    @property
    def metrics(self) -> RouterMetrics:
        return self._metrics

    def route(self, intent: ExecutionIntent) -> RoutingResult:
        """Route an intent based on current authority state."""
        snap = self._store.snapshot
        oa = snap.operator_authority

        # Check live execution
        if snap.live_execution_blocked:
            if oa.practice.value == "ON":
                self._metrics = RouterMetrics(
                    intents_routed=self._metrics.intents_routed + 1,
                    blocked_count=self._metrics.blocked_count,
                    paper_count=self._metrics.paper_count + 1,
                    queued_count=self._metrics.queued_count,
                    executed_count=self._metrics.executed_count,
                )
                return RoutingResult(
                    intent=intent,
                    decision=RouteDecision.PAPER,
                    reason="live_execution BLOCKED, practice ON → paper",
                    adapter_name="paper_broker",
                )
            self._metrics = RouterMetrics(
                intents_routed=self._metrics.intents_routed + 1,
                blocked_count=self._metrics.blocked_count + 1,
                paper_count=self._metrics.paper_count,
                queued_count=self._metrics.queued_count,
                executed_count=self._metrics.executed_count,
            )
            return RoutingResult(
                intent=intent,
                decision=RouteDecision.BLOCKED,
                reason="live_execution BLOCKED, practice OFF → blocked",
            )

        # Get domain trading mode
        from core.contracts.operator_authority import TradingDomain

        domain_key = TradingDomain(intent.domain)
        mode = oa.trading_mode.get(domain_key)
        if mode is None:
            mode_str = "MANUAL"
        else:
            mode_str = mode.value

        # MANUAL → blocked
        if mode_str == "MANUAL":
            self._metrics = RouterMetrics(
                intents_routed=self._metrics.intents_routed + 1,
                blocked_count=self._metrics.blocked_count + 1,
                paper_count=self._metrics.paper_count,
                queued_count=self._metrics.queued_count,
                executed_count=self._metrics.executed_count,
            )
            return RoutingResult(
                intent=intent,
                decision=RouteDecision.BLOCKED,
                reason=f"domain {intent.domain} in MANUAL mode → blocked",
            )

        # SEMI_AUTO → check if exit (auto-fire) or entry (queue)
        if mode_str == "SEMI_AUTO":
            # Exits and risk-reductions auto-fire
            is_exit = intent.side == "SELL"
            if is_exit:
                self._metrics = RouterMetrics(
                    intents_routed=self._metrics.intents_routed + 1,
                    blocked_count=self._metrics.blocked_count,
                    paper_count=self._metrics.paper_count,
                    queued_count=self._metrics.queued_count,
                    executed_count=self._metrics.executed_count + 1,
                )
                return RoutingResult(
                    intent=intent,
                    decision=RouteDecision.EXECUTE,
                    reason="SEMI_AUTO exit → auto-fire",
                    adapter_name="live_adapter",
                )
            # Entries → approval queue
            self._metrics = RouterMetrics(
                intents_routed=self._metrics.intents_routed + 1,
                blocked_count=self._metrics.blocked_count,
                paper_count=self._metrics.paper_count,
                queued_count=self._metrics.queued_count + 1,
                executed_count=self._metrics.executed_count,
            )
            return RoutingResult(
                intent=intent,
                decision=RouteDecision.SEMI_AUTO_QUEUE,
                reason="SEMI_AUTO entry → approval queue",
            )

        # FULL_AUTO → execute
        self._metrics = RouterMetrics(
            intents_routed=self._metrics.intents_routed + 1,
            blocked_count=self._metrics.blocked_count,
            paper_count=self._metrics.paper_count,
            queued_count=self._metrics.queued_count,
            executed_count=self._metrics.executed_count + 1,
        )
        return RoutingResult(
            intent=intent,
            decision=RouteDecision.EXECUTE,
            reason="FULL_AUTO → execute",
            adapter_name="live_adapter",
        )
