"""learning_engine/performance_analysis/archetype_evaluator.py
DIX VISION v42.2 — Archetype Evaluator

Evaluates trading archetypes against historical performance records.
Produces ArchetypeEvaluation summaries that feed into the ArchetypeArena
leaderboard and StrategySynthesizer for next-generation parameter creation.

Pure functions + frozen dataclasses (INV-15). Tier: OFFLINE analytics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ArchetypePerformanceRecord:
    """Performance metrics for one archetype over an evaluation period."""
    archetype_id: str
    strategy_id: str
    total_pnl: float
    num_trades: int
    win_rate: float         # [0, 1]
    sharpe: float
    max_drawdown: float     # positive value, e.g. 0.15 = 15%
    regime: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class ArchetypeEvaluation:
    """Aggregated evaluation of an archetype across multiple strategies."""
    archetype_id: str
    strategy_count: int
    mean_pnl: float
    mean_sharpe: float
    mean_win_rate: float
    mean_drawdown: float
    composite_score: float   # weighted aggregate
    regime_affinity: dict[str, float]   # regime → mean composite score
    ts_ns: int


def _sharpe_from_returns(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / len(returns)
    std = math.sqrt(var) if var > 1e-12 else 1.0
    return mean / std


def evaluate_archetype(
    archetype_id: str,
    records: list[ArchetypePerformanceRecord],
    ts_ns: int,
) -> ArchetypeEvaluation:
    """Aggregate performance records into an ArchetypeEvaluation."""
    relevant = [r for r in records if r.archetype_id == archetype_id]
    if not relevant:
        return ArchetypeEvaluation(
            archetype_id=archetype_id,
            strategy_count=0,
            mean_pnl=0.0,
            mean_sharpe=0.0,
            mean_win_rate=0.0,
            mean_drawdown=0.0,
            composite_score=0.0,
            regime_affinity={},
            ts_ns=ts_ns,
        )

    n = len(relevant)
    mean_pnl = sum(r.total_pnl for r in relevant) / n
    mean_sharpe = sum(r.sharpe for r in relevant) / n
    mean_win_rate = sum(r.win_rate for r in relevant) / n
    mean_drawdown = sum(r.max_drawdown for r in relevant) / n

    # Composite: 40% sharpe (normalised to [0,1]), 30% win_rate, 30% (1 - drawdown)
    sharpe_norm = min(1.0, max(0.0, (mean_sharpe + 3.0) / 6.0))
    dd_score = max(0.0, 1.0 - mean_drawdown)
    composite = 0.4 * sharpe_norm + 0.3 * mean_win_rate + 0.3 * dd_score

    # Regime affinity
    regime_scores: dict[str, list[float]] = {}
    for r in relevant:
        sharpe_norm_r = min(1.0, max(0.0, (r.sharpe + 3.0) / 6.0))
        dd_r = max(0.0, 1.0 - r.max_drawdown)
        score = 0.4 * sharpe_norm_r + 0.3 * r.win_rate + 0.3 * dd_r
        regime_scores.setdefault(r.regime, []).append(score)
    regime_affinity = {
        regime: sum(scores) / len(scores)
        for regime, scores in regime_scores.items()
    }

    return ArchetypeEvaluation(
        archetype_id=archetype_id,
        strategy_count=n,
        mean_pnl=mean_pnl,
        mean_sharpe=mean_sharpe,
        mean_win_rate=mean_win_rate,
        mean_drawdown=mean_drawdown,
        composite_score=composite,
        regime_affinity=regime_affinity,
        ts_ns=ts_ns,
    )


def rank_archetypes(
    evaluations: list[ArchetypeEvaluation],
) -> list[ArchetypeEvaluation]:
    """Sort evaluations by composite_score descending."""
    return sorted(evaluations, key=lambda e: e.composite_score, reverse=True)


__all__ = [
    "ArchetypeEvaluation",
    "ArchetypePerformanceRecord",
    "evaluate_archetype",
    "rank_archetypes",
]
