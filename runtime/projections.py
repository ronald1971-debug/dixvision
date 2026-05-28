"""Read-only projections from RuntimeSnapshot (CONVERGENCE PILLAR 1).

Subsystems don't read the full RuntimeSnapshot — they get typed
projections that expose only what they need. This enforces separation
of concerns and makes dependencies explicit.

Each projection is a frozen dataclass derived from the current snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass

from runtime.authority import RuntimeAuthorityStore

# ---------------------------------------------------------------------------
# Market Projection — for intelligence_engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MarketProjection:
    """What the intelligence engine needs to know about market state."""

    connected: bool
    last_tick_ts_ns: int
    health_score: float


# ---------------------------------------------------------------------------
# Execution Projection — for execution_engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutionProjection:
    """What the execution engine needs to make routing decisions."""

    live_execution_blocked: bool
    system_mode: str
    trading_modes: dict[str, str]
    open_positions: int
    total_exposure_usd: float
    freeze_active: bool


# ---------------------------------------------------------------------------
# Governance Projection — for governance_engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GovernanceProjection:
    """What governance needs for policy evaluation."""

    system_mode: str
    health_score: float
    active_hazards: tuple[str, ...]
    live_execution_blocked: bool
    learning_active: bool
    evolution_active: bool
    operator_id: str
    freeze_active: bool


# ---------------------------------------------------------------------------
# Learning Projection — for learning_engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LearningProjection:
    """What the learning engine needs."""

    learning_active: bool
    evolution_active: bool
    capability_tier: int
    system_mode: str
    freeze_active: bool


# ---------------------------------------------------------------------------
# Projection factory
# ---------------------------------------------------------------------------


class ProjectionFactory:
    """Produces typed projections from the RuntimeAuthorityStore."""

    def __init__(self, store: RuntimeAuthorityStore) -> None:
        self._store = store

    def market(self) -> MarketProjection:
        """Get current market projection."""
        s = self._store.snapshot
        return MarketProjection(
            connected=s.market_connected,
            last_tick_ts_ns=s.last_market_ts_ns,
            health_score=s.health_score,
        )

    def execution(self) -> ExecutionProjection:
        """Get current execution projection."""
        s = self._store.snapshot
        oa = s.operator_authority
        modes = {d.value: oa.trading_mode[d].value for d in oa.trading_mode}
        return ExecutionProjection(
            live_execution_blocked=s.live_execution_blocked,
            system_mode=s.system_mode,
            trading_modes=modes,
            open_positions=s.open_positions,
            total_exposure_usd=s.total_exposure_usd,
            freeze_active=s.freeze_active,
        )

    def governance(self) -> GovernanceProjection:
        """Get current governance projection."""
        s = self._store.snapshot
        return GovernanceProjection(
            system_mode=s.system_mode,
            health_score=s.health_score,
            active_hazards=s.active_hazards,
            live_execution_blocked=s.live_execution_blocked,
            learning_active=s.learning_active,
            evolution_active=s.evolution_active,
            operator_id=s.operator_authority.operator_id,
            freeze_active=s.freeze_active,
        )

    def learning(self) -> LearningProjection:
        """Get current learning projection."""
        s = self._store.snapshot
        return LearningProjection(
            learning_active=s.learning_active,
            evolution_active=s.evolution_active,
            capability_tier=s.current_capability_tier,
            system_mode=s.system_mode,
            freeze_active=s.freeze_active,
        )
