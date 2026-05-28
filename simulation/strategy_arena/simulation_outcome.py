"""simulation/strategy_arena/simulation_outcome.py
DIX VISION v42.2 — Simulation Outcome

Aggregates results from a multi-strategy simulation run into a
SimulationOutcome record. Used by the strategy arena to produce
the final leaderboard and feed scores back into the archetype arena.

Pure functions + frozen dataclasses (INV-15). No IO.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from simulation.scoring_engine import SimulationScore


@dataclass(frozen=True, slots=True)
class StrategyOutcome:
    """Outcome for one strategy in a simulation run."""
    strategy_id: str
    scenario_id: str
    score: SimulationScore
    capital_allocated_usd: float
    final_equity_usd: float
    rank: int
    promoted: bool


@dataclass(frozen=True, slots=True)
class SimulationOutcome:
    """Aggregated outcome of a full simulation arena run."""
    run_id: str
    scenario_ids: tuple[str, ...]
    strategy_outcomes: tuple[StrategyOutcome, ...]
    winner_strategy_id: str
    total_strategies: int
    promoted_count: int
    ts_ns: int

    @property
    def winner(self) -> StrategyOutcome | None:
        for s in self.strategy_outcomes:
            if s.strategy_id == self.winner_strategy_id:
                return s
        return None

    @property
    def leaderboard(self) -> list[StrategyOutcome]:
        return sorted(self.strategy_outcomes, key=lambda s: s.rank)


def build_simulation_outcome(
    scores: list[SimulationScore],
    capital_per_strategy: dict[str, float],
    final_equity_per_strategy: dict[str, float],
    promotion_threshold: float = 0.6,
    ts_ns: int = 0,
) -> SimulationOutcome:
    """
    Build a SimulationOutcome from a list of SimulationScores.

    Args:
        scores:                     Scores from scoring_engine.score_simulation()
        capital_per_strategy:       Allocated capital per strategy_id
        final_equity_per_strategy:  Final equity per strategy_id
        promotion_threshold:        Composite score threshold for promotion
    """
    ranked = sorted(scores, key=lambda s: s.composite_score, reverse=True)
    outcomes: list[StrategyOutcome] = []

    for rank, score in enumerate(ranked, start=1):
        capital = capital_per_strategy.get(score.strategy_id, 0.0)
        final_eq = final_equity_per_strategy.get(score.strategy_id, capital)
        promoted = score.composite_score >= promotion_threshold
        outcomes.append(StrategyOutcome(
            strategy_id=score.strategy_id,
            scenario_id=score.scenario_id,
            score=score,
            capital_allocated_usd=capital,
            final_equity_usd=final_eq,
            rank=rank,
            promoted=promoted,
        ))

    scenario_ids = tuple(sorted({s.scenario_id for s in scores}))
    winner_id = ranked[0].strategy_id if ranked else ""
    promoted_count = sum(1 for o in outcomes if o.promoted)

    return SimulationOutcome(
        run_id=str(uuid.uuid4()),
        scenario_ids=scenario_ids,
        strategy_outcomes=tuple(outcomes),
        winner_strategy_id=winner_id,
        total_strategies=len(outcomes),
        promoted_count=promoted_count,
        ts_ns=ts_ns,
    )


__all__ = [
    "SimulationOutcome",
    "StrategyOutcome",
    "build_simulation_outcome",
]
