"""Market regime embeddings (BUILD-DIRECTIVE §17).

Stores and retrieves market regime embeddings — vector representations
of market conditions (volatility, trend, correlation, liquidity state)
for regime classification and transition detection.

Regimes are the primary context for all strategy decisions. The regime
embedding space allows the system to:
1. Classify current market state
2. Detect regime transitions early
3. Find historically similar regimes
4. Match atoms/strategies to appropriate regimes
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegimeEmbedding:
    """A market regime encoded as a dense vector."""

    regime_id: str
    label: str  # e.g., "TRENDING_BULL", "VOLATILE_CRISIS", "MEAN_REVERT"
    vector: tuple[float, ...]
    volatility: float
    trend_strength: float
    correlation_regime: float  # 0=decorrelated, 1=highly correlated
    liquidity_score: float
    ts_ns: int


@dataclass(frozen=True, slots=True)
class RegimeTransition:
    """Detected transition between regimes."""

    from_regime: str
    to_regime: str
    confidence: float
    transition_speed: float  # 0=gradual, 1=sudden
    ts_ns: int


class MarketRegimeEmbeddingStore:
    """Vector store for market regime embeddings.

    Supports:
    - Classify current market conditions against known regimes
    - Detect regime transitions
    - Find historically similar market states
    - Track regime persistence and frequency
    """

    def __init__(self, *, dimension: int = 32) -> None:
        self._dimension = dimension
        self._regimes: dict[str, RegimeEmbedding] = {}
        self._history: list[RegimeEmbedding] = []
        self._max_history = 10000

    def register_regime(self, regime: RegimeEmbedding) -> None:
        """Register a known regime template."""
        self._regimes[regime.regime_id] = regime

    def record_observation(self, observation: RegimeEmbedding) -> None:
        """Record a market state observation for history."""
        self._history.append(observation)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

    def classify(
        self, current_vector: tuple[float, ...], *, top_k: int = 3
    ) -> list[tuple[RegimeEmbedding, float]]:
        """Classify current market state against known regimes."""
        results: list[tuple[RegimeEmbedding, float]] = []
        for regime in self._regimes.values():
            sim = self._cosine_similarity(current_vector, regime.vector)
            results.append((regime, sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def detect_transition(
        self,
        *,
        previous_vector: tuple[float, ...],
        current_vector: tuple[float, ...],
        threshold: float = 0.3,
        ts_ns: int = 0,
    ) -> RegimeTransition | None:
        """Detect if a regime transition has occurred."""
        # Distance between current and previous
        distance = self._euclidean_distance(previous_vector, current_vector)
        if distance < threshold:
            return None  # no transition

        # Classify both
        prev_class = self.classify(previous_vector, top_k=1)
        curr_class = self.classify(current_vector, top_k=1)

        if not prev_class or not curr_class:
            return None

        from_regime = prev_class[0][0].label
        to_regime = curr_class[0][0].label

        if from_regime == to_regime:
            return None  # same regime, just movement within

        return RegimeTransition(
            from_regime=from_regime,
            to_regime=to_regime,
            confidence=curr_class[0][1],
            transition_speed=min(distance / 1.0, 1.0),
            ts_ns=ts_ns,
        )

    def find_similar_historical(
        self, current_vector: tuple[float, ...], *, top_k: int = 5
    ) -> list[tuple[RegimeEmbedding, float]]:
        """Find historically similar market states."""
        results: list[tuple[RegimeEmbedding, float]] = []
        for obs in self._history:
            sim = self._cosine_similarity(current_vector, obs.vector)
            results.append((obs, sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    @property
    def regime_count(self) -> int:
        """Number of registered regimes."""
        return len(self._regimes)

    @property
    def history_size(self) -> int:
        """Number of historical observations."""
        return len(self._history)

    @staticmethod
    def _cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        min_len = min(len(a), len(b))
        if min_len == 0:
            return 0.0
        dot = sum(a[i] * b[i] for i in range(min_len))
        norm_a = math.sqrt(sum(x * x for x in a[:min_len]))
        norm_b = math.sqrt(sum(x * x for x in b[:min_len]))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _euclidean_distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        min_len = min(len(a), len(b))
        if min_len == 0:
            return 0.0
        return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(min_len)))
