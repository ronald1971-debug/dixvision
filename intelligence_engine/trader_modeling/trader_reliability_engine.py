"""Trader reliability engine (BUILD-DIRECTIVE §15 — TIS module 10).

Maintains a dynamic reliability score for each trader that influences
how much weight their atoms receive in composition. Reliability is
distinct from credibility — it tracks ongoing prediction accuracy,
not historical reputation.

Reliability decays over time if a trader stops being accurate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(slots=True)
class ReliabilityState:
    """Mutable reliability state for a single trader."""

    trader_id: str
    correct_predictions: int = 0
    total_predictions: int = 0
    streak_current: int = 0  # positive = wins, negative = losses
    streak_best: int = 0
    regime_reliability: dict[str, float] = field(default_factory=dict)
    last_update_ts_ns: int = 0


class TraderReliabilityEngine:
    """Tracks ongoing reliability of trader signals/atoms.

    Unlike credibility (which is historical/static), reliability
    changes with every new observation. A legendary trader who
    enters a drawdown sees their reliability drop, reducing their
    atoms' weight in composition until they recover.
    """

    def __init__(self, *, decay_halflife_days: float = 30.0) -> None:
        self._decay_halflife_ns = int(decay_halflife_days * 86400 * 1e9)
        self._states: dict[str, ReliabilityState] = {}

    def record_outcome(
        self,
        *,
        trader_id: str,
        correct: bool,
        regime: str = "",
        ts_ns: int = 0,
    ) -> float:
        """Record a prediction outcome. Returns updated reliability score."""
        state = self._states.setdefault(trader_id, ReliabilityState(trader_id=trader_id))
        state.total_predictions += 1
        if correct:
            state.correct_predictions += 1
            state.streak_current = max(0, state.streak_current) + 1
        else:
            state.streak_current = min(0, state.streak_current) - 1

        state.streak_best = max(state.streak_best, state.streak_current)
        state.last_update_ts_ns = ts_ns

        # Update regime-specific reliability
        if regime:
            regime_state = state.regime_reliability.get(regime, 0.5)
            alpha = 0.1  # EMA smoothing
            new_val = alpha * (1.0 if correct else 0.0) + (1 - alpha) * regime_state
            state.regime_reliability[regime] = new_val

        return self.reliability_score(trader_id, ts_ns=ts_ns)

    def reliability_score(self, trader_id: str, *, ts_ns: int = 0) -> float:
        """Get current reliability score for a trader."""
        state = self._states.get(trader_id)
        if state is None or state.total_predictions == 0:
            return 0.5  # prior: neutral

        base_score = state.correct_predictions / state.total_predictions

        # Apply time decay if stale
        if ts_ns > 0 and state.last_update_ts_ns > 0:
            age_ns = ts_ns - state.last_update_ts_ns
            if age_ns > 0 and self._decay_halflife_ns > 0:
                decay = math.exp(-0.693 * age_ns / self._decay_halflife_ns)
                # Decay toward 0.5 (neutral)
                base_score = 0.5 + (base_score - 0.5) * decay

        # Streak bonus/penalty (small)
        streak_factor = state.streak_current * 0.01
        score = base_score + streak_factor

        return max(0.0, min(1.0, score))

    def get_regime_reliability(self, trader_id: str, regime: str) -> float:
        """Get reliability for a specific regime."""
        state = self._states.get(trader_id)
        if state is None:
            return 0.5
        return state.regime_reliability.get(regime, 0.5)

    def get_top_reliable(self, *, n: int = 10, regime: str = "") -> list[str]:
        """Get the most reliable traders, optionally for a specific regime."""
        scored: list[tuple[str, float]] = []
        for trader_id, state in self._states.items():
            if state.total_predictions < 5:
                continue
            if regime:
                score = state.regime_reliability.get(regime, 0.0)
            else:
                score = state.correct_predictions / state.total_predictions
            scored.append((trader_id, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in scored[:n]]

    @property
    def tracked_count(self) -> int:
        """Number of traders being tracked."""
        return len(self._states)
