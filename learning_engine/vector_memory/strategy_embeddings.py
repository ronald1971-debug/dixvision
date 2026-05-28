"""Strategy atom embeddings (BUILD-DIRECTIVE §17).

Stores strategy atom vectors for:
- Regime-aware strategy recommendation
- Atom compatibility checking before composition
- Performance-indexed retrieval
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class StrategyEmbeddingRecord:
    """A stored strategy atom embedding."""

    atom_id: str
    vector: tuple[float, ...]
    category: str
    source_trader: str
    applicable_regimes: tuple[str, ...]
    backtest_sharpe: float = 0.0


class StrategyEmbeddingStore:
    """Vector store for strategy atom embeddings."""

    def __init__(self, *, dimension: int = 8) -> None:
        self._dimension = dimension
        self._records: list[StrategyEmbeddingRecord] = []
        self._vectors: list[np.ndarray] = []

    def add(self, record: StrategyEmbeddingRecord) -> None:
        """Add a strategy embedding."""
        vec = np.array(record.vector, dtype=np.float32)
        if vec.shape[0] != self._dimension:
            msg = f"expected dim={self._dimension}, got {vec.shape[0]}"
            raise ValueError(msg)
        self._records.append(record)
        self._vectors.append(vec)

    def search_by_regime(
        self,
        query: tuple[float, ...],
        *,
        regime: str,
        top_k: int = 5,
    ) -> list[tuple[StrategyEmbeddingRecord, float]]:
        """Find top-k strategies applicable to a regime."""
        if not self._vectors:
            return []
        q = np.array(query, dtype=np.float32)
        q_norm = q / (np.linalg.norm(q) + 1e-10)

        scores = []
        for i, v in enumerate(self._vectors):
            rec = self._records[i]
            if regime not in rec.applicable_regimes and "ALL" not in rec.applicable_regimes:
                continue
            v_norm = v / (np.linalg.norm(v) + 1e-10)
            sim = float(np.dot(q_norm, v_norm))
            scores.append((i, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [(self._records[idx], score) for idx, score in scores[:top_k]]

    @property
    def size(self) -> int:
        """Number of strategy embeddings stored."""
        return len(self._records)
