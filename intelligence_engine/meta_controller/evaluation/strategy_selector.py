"""
intelligence_engine/meta_controller/evaluation/strategy_selector.py
DIX VISION v42.2 — Strategy Selector

Selects the top-K strategies from a pool based on a composite
performance score. Called by the meta-controller orchestrator after
each evaluation round to promote the best-performing strategies.

composite_score = 0.4 * sharpe_norm + 0.3 * win_rate + 0.3 * regime_fit
All inputs are expected in [0, 1] range (callers normalise).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class StrategyScore:
    """Performance score for a single strategy."""
    strategy_id: str
    sharpe: float          # normalised to [0, 1]
    win_rate: float        # [0, 1]
    regime_fit: float      # [0, 1] — how well strategy fits current regime
    composite_score: float = 0.0

    def __post_init__(self) -> None:
        # Compute composite if caller left it at 0.0
        if self.composite_score == 0.0:
            object.__setattr__(
                self,
                "composite_score",
                0.4 * self.sharpe + 0.3 * self.win_rate + 0.3 * self.regime_fit,
            )


class StrategySelector:
    """
    Selects top-K strategies by composite score.

    Thread-safe. Scores are registered via register_score() and
    retrieved via select().
    """

    def __init__(self, top_k: int = 3) -> None:
        self._top_k = top_k
        self._lock = threading.Lock()
        # strategy_id → latest StrategyScore
        self._scores: dict[str, StrategyScore] = {}

    def register_score(self, score: StrategyScore) -> None:
        """Update the score for a strategy."""
        with self._lock:
            self._scores[score.strategy_id] = score

    def select(self) -> list[StrategyScore]:
        """Return up to top_k strategies sorted by composite_score desc."""
        with self._lock:
            ranked = sorted(
                self._scores.values(),
                key=lambda s: s.composite_score,
                reverse=True,
            )
        return ranked[: self._top_k]

    def best(self) -> StrategyScore | None:
        """Return the single highest-scoring strategy."""
        selected = self.select()
        return selected[0] if selected else None

    def all_scores(self) -> list[StrategyScore]:
        with self._lock:
            return list(self._scores.values())

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "registered": len(self._scores),
                "top_k": self._top_k,
                "top": [s.strategy_id for s in self.select()],
            }


__all__ = ["StrategyScore", "StrategySelector"]
