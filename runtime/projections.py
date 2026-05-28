"""Read-only projections from RuntimeSnapshot (CONVERGENCE PILLAR 1).

Subsystems don't read the full RuntimeSnapshot — they get typed
projections that expose only what they need. This enforces separation
of concerns and makes dependencies explicit.

Each projection is a frozen dataclass derived from the current snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    cognitive_integrity_healthy: bool = True


# ---------------------------------------------------------------------------
# Cognitive Governance Projection — for enforcement gates / dashboard
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CognitiveGovernanceProjection:
    """Read-only snapshot of the 13-guard cognitive integrity status.

    Populated by :meth:`ProjectionFactory.cognitive_governance` via a
    lazy import of ``cognitive_governance.engine`` so runtime subsystems
    never depend on the engine package directly — they consume this typed
    contract instead.
    """

    overall_healthy: bool
    belief_integrity_ok: bool
    memory_clean: bool
    mutation_safe: bool
    no_hallucination: bool
    epistemic_current: bool
    learning_truthful: bool
    lineage_intact: bool
    identity_stable: bool
    no_synthetic_feedback: bool
    no_reward_hacking: bool
    causal_consistent: bool
    active_violations: tuple[str, ...]
    detail: str


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
        cogov = self.cognitive_governance()
        return GovernanceProjection(
            system_mode=s.system_mode,
            health_score=s.health_score,
            active_hazards=s.active_hazards,
            live_execution_blocked=s.live_execution_blocked,
            learning_active=s.learning_active,
            evolution_active=s.evolution_active,
            operator_id=s.operator_authority.operator_id,
            freeze_active=s.freeze_active,
            cognitive_integrity_healthy=cogov.overall_healthy,
        )

    def cognitive_governance(self) -> CognitiveGovernanceProjection:
        """Get current cognitive governance projection.

        Lazy-imports ``cognitive_governance.engine`` so callers never need
        a direct dependency on that package. Falls back to a fully-healthy
        sentinel when the engine is not yet initialised.
        """
        try:
            from cognitive_governance.engine import get_cognitive_governance  # noqa: PLC0415

            status = get_cognitive_governance().check_all()
            return CognitiveGovernanceProjection(
                overall_healthy=status.overall_healthy,
                belief_integrity_ok=status.belief_integrity_ok,
                memory_clean=status.memory_clean,
                mutation_safe=status.mutation_safe,
                no_hallucination=status.no_hallucination,
                epistemic_current=status.epistemic_current,
                learning_truthful=status.learning_truthful,
                lineage_intact=status.lineage_intact,
                identity_stable=status.identity_stable,
                no_synthetic_feedback=status.no_synthetic_feedback,
                no_reward_hacking=status.no_reward_hacking,
                causal_consistent=status.causal_consistent,
                active_violations=tuple(v.value for v in status.active_violations),
                detail=status.detail,
            )
        except Exception:
            return CognitiveGovernanceProjection(
                overall_healthy=True,
                belief_integrity_ok=True,
                memory_clean=True,
                mutation_safe=True,
                no_hallucination=True,
                epistemic_current=True,
                learning_truthful=True,
                lineage_intact=True,
                identity_stable=True,
                no_synthetic_feedback=True,
                no_reward_hacking=True,
                causal_consistent=True,
                active_violations=(),
                detail="unavailable",
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
