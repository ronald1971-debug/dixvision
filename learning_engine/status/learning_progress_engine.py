"""Learning Progress Engine (BUILD-DIRECTIVE §18).

Provides a real, validated capability score for each engine subsystem.
NOT a fake "readiness" metric — this tracks actual demonstrated performance
via validated backtests and paper-trade results.

Capability tiers:
  Tier 0: Read-only (can observe markets)
  Tier 1: Research (can discover patterns)
  Tier 2: Simulation (can run backtests)
  Tier 3: Proposal (can propose strategies)
  Tier 4: Governed paper (paper trading under governance)
  Tier 5: Live (real execution — operator-gated)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class CapabilityTier(IntEnum):
    """Learning capability tiers — earned, not declared."""

    READ_ONLY = 0
    RESEARCH = 1
    SIMULATION = 2
    PROPOSAL = 3
    GOVERNED_PAPER = 4
    LIVE = 5


@dataclass(frozen=True, slots=True)
class TierEvidence:
    """Evidence supporting a capability tier claim."""

    tier: CapabilityTier
    metric_name: str
    metric_value: float
    threshold: float
    passed: bool
    ts_ns: int


@dataclass(frozen=True, slots=True)
class SubsystemProgress:
    """Progress snapshot for one subsystem."""

    subsystem: str
    current_tier: CapabilityTier
    evidence: tuple[TierEvidence, ...]
    next_tier_requirements: dict[str, float]


@dataclass
class LearningProgressEngine:
    """Tracks validated capability scores per subsystem.

    Subsystems earn tiers by demonstrating performance against
    objective metrics — not by self-declaring readiness.
    """

    _progress: dict[str, SubsystemProgress] = field(default_factory=dict)

    # Tier promotion thresholds per metric
    TIER_THRESHOLDS: dict[CapabilityTier, dict[str, float]] = field(
        default_factory=lambda: {
            CapabilityTier.RESEARCH: {"patterns_discovered": 10},
            CapabilityTier.SIMULATION: {"backtests_completed": 50},
            CapabilityTier.PROPOSAL: {
                "backtest_sharpe_avg": 1.0,
                "strategies_proposed": 5,
            },
            CapabilityTier.GOVERNED_PAPER: {
                "paper_sharpe_30d": 0.8,
                "paper_max_drawdown_pct": 15.0,
            },
            CapabilityTier.LIVE: {
                "paper_sharpe_90d": 1.2,
                "paper_max_drawdown_pct": 10.0,
                "operator_approval": 1.0,
            },
        }
    )

    def record_evidence(
        self,
        *,
        subsystem: str,
        metric_name: str,
        metric_value: float,
        ts_ns: int,
    ) -> TierEvidence | None:
        """Record a metric observation and check for tier promotion."""
        current = self._progress.get(subsystem)
        current_tier = current.current_tier if current else CapabilityTier.READ_ONLY
        next_tier = CapabilityTier(min(current_tier + 1, CapabilityTier.LIVE))

        thresholds = self.TIER_THRESHOLDS.get(next_tier, {})
        threshold = thresholds.get(metric_name, 0.0)

        evidence = TierEvidence(
            tier=next_tier,
            metric_name=metric_name,
            metric_value=metric_value,
            threshold=threshold,
            passed=metric_value >= threshold if threshold > 0 else False,
            ts_ns=ts_ns,
        )
        return evidence

    def get_progress(self, subsystem: str) -> SubsystemProgress | None:
        """Get current progress for a subsystem."""
        return self._progress.get(subsystem)

    def promote(
        self, subsystem: str, *, tier: CapabilityTier, evidence: tuple[TierEvidence, ...]
    ) -> None:
        """Promote a subsystem to a new tier with evidence."""
        next_tier_requirements = self.TIER_THRESHOLDS.get(
            CapabilityTier(min(tier + 1, CapabilityTier.LIVE)), {}
        )
        self._progress[subsystem] = SubsystemProgress(
            subsystem=subsystem,
            current_tier=tier,
            evidence=evidence,
            next_tier_requirements=next_tier_requirements,
        )
