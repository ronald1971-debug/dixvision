"""Pattern encoder (BUILD-DIRECTIVE §16 — Trader Abstraction module 2).

Encodes extracted trader patterns into dense vector representations
suitable for storage in vector memory and similarity search.

Patterns → embeddings → FAISS index → retrieval during composition.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EncodedPattern:
    """A trader pattern encoded as a vector."""

    pattern_id: str
    trader_id: str
    pattern_type: str  # ENTRY, EXIT, SIZING, REGIME_SWITCH, etc.
    embedding: tuple[float, ...]
    quality_score: float  # 0-1 based on frequency × success rate
    regime_specificity: float  # 0=generalist, 1=regime-specific
    ts_ns: int


class PatternEncoder:
    """Encodes trader patterns into vector representations.

    The encoding captures:
    - Pattern type (one-hot across categories)
    - Success rate (continuous)
    - Regime applicability (multi-hot across regimes)
    - Condition thresholds (normalized)
    - Temporal features (frequency, recency)
    """

    # Known regimes for encoding
    REGIMES = (
        "TRENDING_BULL",
        "TRENDING_BEAR",
        "VOLATILE",
        "MEAN_REVERT",
        "CRISIS",
        "ACCUMULATION",
        "DISTRIBUTION",
        "RANGING",
    )

    PATTERN_TYPES = (
        "ENTRY",
        "EXIT",
        "SIZING",
        "TIMING",
        "FILTER",
        "RISK",
        "REGIME_SWITCH",
        "RISK_ADJUSTMENT",
        "CONVICTION_SCALE",
    )

    def __init__(self, *, dimension: int = 32) -> None:
        self._dimension = dimension

    def encode(
        self,
        *,
        pattern_id: str,
        trader_id: str,
        pattern_type: str,
        success_rate: float,
        frequency: int,
        applicable_regimes: list[str],
        conditions: dict[str, float],
        ts_ns: int = 0,
    ) -> EncodedPattern:
        """Encode a pattern into a vector representation."""
        components: list[float] = []

        # Pattern type one-hot (9 dims)
        for pt in self.PATTERN_TYPES:
            components.append(1.0 if pt == pattern_type.upper() else 0.0)

        # Success rate (1 dim)
        components.append(success_rate)

        # Frequency (1 dim, log-scaled)
        components.append(math.log1p(frequency) / 5.0)

        # Regime applicability multi-hot (8 dims)
        regime_set = set(r.upper() for r in applicable_regimes)
        for regime in self.REGIMES:
            components.append(1.0 if regime in regime_set else 0.0)

        # Condition values (pad to fixed length, 8 dims)
        sorted_conditions = sorted(conditions.items())[:8]
        for _, val in sorted_conditions:
            components.append(min(abs(val) / 100.0, 1.0))
        while len(components) < 9 + 1 + 1 + 8 + 8:
            components.append(0.0)

        # Pad or truncate to target dimension
        if len(components) < self._dimension:
            components.extend([0.0] * (self._dimension - len(components)))
        embedding = tuple(components[: self._dimension])

        # Quality score
        quality = success_rate * min(frequency / 10.0, 1.0)

        # Regime specificity
        regime_specificity = 1.0 - (len(applicable_regimes) / max(len(self.REGIMES), 1))

        return EncodedPattern(
            pattern_id=pattern_id,
            trader_id=trader_id,
            pattern_type=pattern_type,
            embedding=embedding,
            quality_score=quality,
            regime_specificity=regime_specificity,
            ts_ns=ts_ns,
        )

    def batch_encode(self, patterns: list[dict[str, object]]) -> list[EncodedPattern]:
        """Encode a batch of patterns."""
        results: list[EncodedPattern] = []
        for p in patterns:
            encoded = self.encode(
                pattern_id=str(p.get("pattern_id", "")),
                trader_id=str(p.get("trader_id", "")),
                pattern_type=str(p.get("pattern_type", "ENTRY")),
                success_rate=float(p.get("success_rate", 0.5)),
                frequency=int(p.get("frequency", 1)),
                applicable_regimes=list(p.get("applicable_regimes", [])),  # type: ignore[arg-type]
                conditions=dict(p.get("conditions", {})),  # type: ignore[arg-type]
                ts_ns=int(p.get("ts_ns", 0)),
            )
            results.append(encoded)
        return results
