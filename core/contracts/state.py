"""core.contracts.state — SystemState Protocol & Value Types (System Spec §FSM).

Production-grade state management contracts. SystemMode is the FSM with states
LOCKED → SAFE → PAPER → CANARY → LIVE → AUTO. Only StateTransitionManager
may mutate SystemMode (INV-56 Triad Lock).

The RuntimeSnapshot is the single authoritative read-only view consumed by all
subsystems. Written ONLY by governance + operator_bridge (Convergence Pillar 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Protocol, runtime_checkable

from system import time_source


class SystemMode(StrEnum):
    """FSM states — promotion requires OperatorConsent via StateTransitionManager."""

    LOCKED = "LOCKED"
    SAFE_MODE = "SAFE_MODE"
    PAPER = "PAPER"
    CANARY = "CANARY"
    LIVE = "LIVE"
    AUTO = "AUTO"
    DEGRADED = "DEGRADED"
    EMERGENCY_HALT = "EMERGENCY_HALT"


class HealthLevel(IntEnum):
    """Subsystem health grades — drives drift oracle downgrade decisions."""

    CRITICAL = 0
    DEGRADED = 1
    MARGINAL = 2
    HEALTHY = 3
    OPTIMAL = 4


class EngineStatus(StrEnum):
    """Individual engine lifecycle status."""

    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    HALTING = "HALTING"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class EngineHealth:
    """Health report for a single engine."""

    engine_id: str
    status: EngineStatus
    health: HealthLevel
    last_heartbeat_ns: int
    error_count_1m: int = 0
    latency_p99_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """Current portfolio state — read-only, sourced from execution_engine."""

    total_equity_usd: float
    unrealized_pnl_usd: float
    realized_pnl_today_usd: float
    open_positions: int
    exposure_ratio: float
    max_drawdown_session_pct: float
    ts_ns: int = field(default_factory=time_source.wall_ns)


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    """Single authoritative state consumed by all subsystems (Convergence Pillar 1).

    Only governance_engine + operator_bridge write to this. Every other module
    reads a frozen copy. Replaces scattered state in system/state.py and
    system_engine/state/.
    """

    mode: SystemMode
    engines: tuple[EngineHealth, ...]
    portfolio: PortfolioSnapshot
    tick_count: int
    session_start_ns: int
    last_governance_decision_ns: int
    drift_score: float = 0.0
    hazard_active: bool = False
    kill_switch_armed: bool = True
    ts_ns: int = field(default_factory=time_source.wall_ns)

    @property
    def overall_health(self) -> HealthLevel:
        """Minimum health across all engines."""
        if not self.engines:
            return HealthLevel.HEALTHY
        return HealthLevel(min(e.health for e in self.engines))

    @property
    def is_live(self) -> bool:
        """Whether system is in a live execution mode."""
        from core.contracts.mode_effects import effect_for

        eff = effect_for(self.mode)
        return eff.executions_dispatch and eff.size_cap_pct is None

    @property
    def is_paper(self) -> bool:
        """Whether system is in paper/canary (non-live) execution mode."""
        from core.contracts.mode_effects import effect_for

        eff = effect_for(self.mode)
        return eff.signals_emit and not self.is_live


@runtime_checkable
class IState(Protocol):
    """Protocol: state management contract.

    Concrete implementation is StateTransitionManager in governance_engine.
    Only this manager may mutate SystemMode (INV-56 Triad Lock enforced).
    """

    def get_snapshot(self) -> RuntimeSnapshot:
        """Return the current frozen RuntimeSnapshot.

        All consumers read from this. Never stale by more than one tick.
        """
        ...

    def get_mode(self) -> SystemMode:
        """Return the current system mode without full snapshot overhead."""
        ...

    def transition(self, target: SystemMode, *, reason: str, operator_id: str) -> bool:
        """Request mode transition via StateTransitionManager.

        Args:
            target: Desired next mode.
            reason: Human-readable reason (logged to authority ledger).
            operator_id: Must match OperatorAuthority.operator_id.

        Returns:
            True if transition succeeded, False if rejected by FSM rules.
        """
        ...

    def update_engine_health(self, health: EngineHealth) -> None:
        """Update a single engine's health in the runtime snapshot."""
        ...

    def update_portfolio(self, portfolio: PortfolioSnapshot) -> None:
        """Update the portfolio snapshot from execution_engine."""
        ...

    @property
    def session_start_ns(self) -> int:
        """Nanosecond timestamp when this session started."""
        ...


@runtime_checkable
class IStateReader(Protocol):
    """Read-only protocol for subsystems that only need to observe state."""

    def get_snapshot(self) -> RuntimeSnapshot:
        """Return the current frozen RuntimeSnapshot."""
        ...

    def get_mode(self) -> SystemMode:
        """Return the current system mode."""
        ...


__all__ = [
    "EngineHealth",
    "EngineStatus",
    "HealthLevel",
    "IState",
    "IStateReader",
    "PortfolioSnapshot",
    "RuntimeSnapshot",
    "SystemMode",
]
