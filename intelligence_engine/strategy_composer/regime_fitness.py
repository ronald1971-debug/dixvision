"""Regime fitness (BUILD-DIRECTIVE §20 — Strategy Composer module 3).

Tracks per-regime performance of strategy atoms and composed strategies.
Used by the composer to select atoms that perform best in the current
regime, and by the meta-controller to weight allocations.

Every atom carries a regime_fitness dict. This module maintains and
updates those scores based on actual performance data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RegimeFitnessScore:
    """Fitness of an atom/strategy in a specific regime."""

    entity_id: str
    regime: str
    score: float  # 0=terrible, 1=excellent
    sample_size: int
    confidence: float  # how confident we are in this score
    last_updated_ts_ns: int


@dataclass(slots=True)
class FitnessState:
    """Internal mutable state for fitness tracking."""

    scores: list[float] = field(default_factory=list)
    last_ts_ns: int = 0


class RegimeFitnessTracker:
    """Tracks and updates regime fitness for atoms and strategies.

    The tracker uses exponential moving average (EMA) to adapt quickly
    to regime changes while maintaining stability.
    """

    def __init__(self, *, ema_alpha: float = 0.1, min_samples: int = 5) -> None:
        self._ema_alpha = ema_alpha
        self._min_samples = min_samples
        # entity_id → regime → FitnessState
        self._states: dict[str, dict[str, FitnessState]] = {}

    def update(
        self,
        *,
        entity_id: str,
        regime: str,
        outcome: float,  # normalized: -1=worst, +1=best
        ts_ns: int = 0,
    ) -> RegimeFitnessScore:
        """Record an outcome and return updated fitness score."""
        regime_states = self._states.setdefault(entity_id, {})
        state = regime_states.get(regime)
        if state is None:
            state = FitnessState()
            regime_states[regime] = state

        state.scores.append(outcome)
        state.last_ts_ns = ts_ns

        # Compute fitness via EMA
        if len(state.scores) == 1:
            ema = state.scores[0]
        else:
            ema = state.scores[-2] if len(state.scores) >= 2 else 0.0
            ema = self._ema_alpha * outcome + (1 - self._ema_alpha) * ema

        # Normalize to 0-1
        normalized = (ema + 1.0) / 2.0
        normalized = max(0.0, min(1.0, normalized))

        # Confidence based on sample size
        n = len(state.scores)
        confidence = min(n / (self._min_samples * 2.0), 1.0)

        return RegimeFitnessScore(
            entity_id=entity_id,
            regime=regime,
            score=normalized,
            sample_size=n,
            confidence=confidence,
            last_updated_ts_ns=ts_ns,
        )

    def get_fitness(self, entity_id: str, regime: str) -> RegimeFitnessScore | None:
        """Get current fitness score for entity in regime."""
        regime_states = self._states.get(entity_id, {})
        state = regime_states.get(regime)
        if state is None or not state.scores:
            return None

        # Recalculate EMA
        ema = state.scores[0]
        for s in state.scores[1:]:
            ema = self._ema_alpha * s + (1 - self._ema_alpha) * ema

        normalized = max(0.0, min(1.0, (ema + 1.0) / 2.0))
        confidence = min(len(state.scores) / (self._min_samples * 2.0), 1.0)

        return RegimeFitnessScore(
            entity_id=entity_id,
            regime=regime,
            score=normalized,
            sample_size=len(state.scores),
            confidence=confidence,
            last_updated_ts_ns=state.last_ts_ns,
        )

    def get_top_for_regime(
        self, regime: str, *, top_n: int = 10, min_confidence: float = 0.3
    ) -> list[RegimeFitnessScore]:
        """Get top-performing entities for a regime."""
        results: list[RegimeFitnessScore] = []
        for entity_id in self._states:
            score = self.get_fitness(entity_id, regime)
            if score is not None and score.confidence >= min_confidence:
                results.append(score)
        results.sort(key=lambda s: s.score, reverse=True)
        return results[:top_n]

    def get_all_regimes(self, entity_id: str) -> dict[str, float]:
        """Get fitness scores across all regimes for an entity."""
        regime_states = self._states.get(entity_id, {})
        result: dict[str, float] = {}
        for regime in regime_states:
            score = self.get_fitness(entity_id, regime)
            if score is not None:
                result[regime] = score.score
        return result

    def cross_regime_robustness(self, entity_id: str) -> float:
        """Score how robust an entity is across all regimes (0=specialist, 1=generalist)."""
        scores = self.get_all_regimes(entity_id)
        if len(scores) < 2:
            return 0.0
        values = list(scores.values())
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        # Low variance = robust across regimes
        std = math.sqrt(variance)
        return max(0.0, 1.0 - std * 2.0)  # normalize: std=0 → 1.0, std≥0.5 → 0.0
