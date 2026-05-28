"""Philosophy encoder (BUILD-DIRECTIVE §16 — Trader Abstraction module 3).

Encodes trader philosophies into vector representations for the
vector memory store. Philosophies influence how the meta-controller
weights signals — a trader whose philosophy aligns with the current
regime gets higher weight.

Distinct from intelligence_engine/trader_modeling/philosophy_encoder.py
which produces PhilosophyVector dataclasses. This module produces
raw embeddings for FAISS indexing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PhilosophyEmbedding:
    """A trader philosophy encoded for vector storage."""

    trader_id: str
    embedding: tuple[float, ...]
    risk_dimension: float  # conservative ↔ aggressive
    time_dimension: float  # short-term ↔ long-term
    systematic_dimension: float  # discretionary ↔ systematic
    conviction_dimension: float  # diversified ↔ concentrated


class PhilosophyEmbeddingEncoder:
    """Encodes philosophies into embeddings for vector memory.

    Dimensions encode:
    - Risk appetite (conservative to aggressive)
    - Time preference (scalp to invest)
    - Systematic vs discretionary
    - Concentration vs diversification
    - Market model (trend, mean-revert, event, arb)
    - Domain expertise weights
    """

    MARKET_MODELS = (
        "trend_following",
        "mean_reversion",
        "event_driven",
        "arbitrage",
        "market_making",
        "momentum",
        "value",
        "macro",
        "statistical",
    )

    DOMAINS = (
        "crypto",
        "equities",
        "forex",
        "commodities",
        "fixed_income",
        "derivatives",
        "defi",
    )

    def __init__(self, *, dimension: int = 48) -> None:
        self._dimension = dimension

    def encode(
        self,
        *,
        trader_id: str,
        risk_tolerance: float,  # 0=conservative, 1=aggressive
        time_horizon: float,  # 0=scalper, 1=long-term investor
        systematic_score: float,  # 0=discretionary, 1=fully systematic
        conviction_style: float,  # 0=diversified, 1=concentrated
        market_models: list[str],
        domain_weights: dict[str, float],
        beliefs: list[str] | None = None,
    ) -> PhilosophyEmbedding:
        """Encode a philosophy into a vector."""
        components: list[float] = []

        # Core dimensions (4 dims)
        components.append(risk_tolerance)
        components.append(time_horizon)
        components.append(systematic_score)
        components.append(conviction_style)

        # Market model multi-hot (9 dims)
        model_set = set(m.lower() for m in market_models)
        for model in self.MARKET_MODELS:
            components.append(1.0 if model in model_set else 0.0)

        # Domain weights (7 dims)
        for domain in self.DOMAINS:
            components.append(domain_weights.get(domain, 0.0))

        # Belief features (hashed into fixed dims, 8 dims)
        belief_hash = [0.0] * 8
        if beliefs:
            for _i, belief in enumerate(beliefs[:8]):
                # Simple hash-based encoding
                h = sum(ord(c) for c in belief) % 8
                belief_hash[h] += 1.0 / max(len(beliefs), 1)
        components.extend(belief_hash)

        # Derived features (4 dims)
        # Aggressiveness = risk × conviction
        components.append(risk_tolerance * conviction_style)
        # Patience = time_horizon × (1 - risk)
        components.append(time_horizon * (1.0 - risk_tolerance))
        # Adaptability proxy = number of models
        components.append(min(len(market_models) / 3.0, 1.0))
        # Specialization = max domain weight
        components.append(max(domain_weights.values()) if domain_weights else 0.0)

        # Pad/truncate
        if len(components) < self._dimension:
            components.extend([0.0] * (self._dimension - len(components)))
        embedding = tuple(components[: self._dimension])

        return PhilosophyEmbedding(
            trader_id=trader_id,
            embedding=embedding,
            risk_dimension=risk_tolerance,
            time_dimension=time_horizon,
            systematic_dimension=systematic_score,
            conviction_dimension=conviction_style,
        )

    def similarity(self, a: PhilosophyEmbedding, b: PhilosophyEmbedding) -> float:
        """Compute similarity between two philosophy embeddings."""
        return self._cosine_similarity(a.embedding, b.embedding)

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
