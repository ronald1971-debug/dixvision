"""learning_engine/trader_abstraction/embedder.py
DIX VISION v42.2 — Trader Abstraction Embedder

Projects encoded trader observations into a lower-dimensional
embedding space using a simple linear projection (PCA-like).
Embeddings are used for archetype clustering, similarity search,
and experience retrieval.

Pure functions + frozen dataclasses (INV-15). No IO, no clock reads.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EmbedderConfig:
    """Configuration for the embedding projection."""
    input_dim: int = 64
    embed_dim: int = 16
    normalise_output: bool = True


@dataclass(frozen=True, slots=True)
class TraderEmbedding:
    """Low-dimensional embedding of a trader observation."""
    strategy_id: str
    embedding: tuple[float, ...]
    source_dim: int
    embed_dim: int
    ts_ns: int


def _dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(v: tuple[float, ...]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    na = _norm(a)
    nb = _norm(b)
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return _dot(a, b) / (na * nb)


class TraderEmbedder:
    """
    Projects feature vectors into embedding space via random projection.

    Uses a fixed random orthogonal projection matrix seeded by a
    deterministic seed (INV-15). The same projection is applied to
    every observation, allowing cosine similarity comparisons.
    """

    def __init__(self, config: EmbedderConfig | None = None, seed: int = 42) -> None:
        self._cfg = config or EmbedderConfig()
        self._projection = self._build_projection(seed)

    def _build_projection(self, seed: int) -> list[list[float]]:
        """Build a deterministic random projection matrix."""
        import hashlib
        rows: list[list[float]] = []
        for i in range(self._cfg.embed_dim):
            row = []
            for j in range(self._cfg.input_dim):
                h = hashlib.md5(f"{seed}:{i}:{j}".encode()).digest()
                val = (int.from_bytes(h[:4], "big") / 0xFFFFFFFF) * 2.0 - 1.0
                row.append(val)
            # Normalise row to unit length
            rn = math.sqrt(sum(x * x for x in row)) or 1.0
            rows.append([x / rn for x in row])
        return rows

    def embed(
        self,
        strategy_id: str,
        features: tuple[float, ...],
        ts_ns: int,
    ) -> TraderEmbedding:
        """Project features into embedding space."""
        d_in = len(features)
        proj = self._projection
        embedding_vals: list[float] = []
        for row in proj:
            s = sum(row[j] * features[j] for j in range(min(d_in, len(row))))
            embedding_vals.append(s)

        if self._cfg.normalise_output:
            n = math.sqrt(sum(x * x for x in embedding_vals)) or 1.0
            embedding_vals = [x / n for x in embedding_vals]

        return TraderEmbedding(
            strategy_id=strategy_id,
            embedding=tuple(embedding_vals),
            source_dim=d_in,
            embed_dim=self._cfg.embed_dim,
            ts_ns=ts_ns,
        )

    @staticmethod
    def cosine_similarity(a: TraderEmbedding, b: TraderEmbedding) -> float:
        return _cosine_similarity(a.embedding, b.embedding)

    def nearest(
        self,
        query: TraderEmbedding,
        candidates: list[TraderEmbedding],
        top_k: int = 5,
    ) -> list[tuple[float, TraderEmbedding]]:
        """Return top-k most similar embeddings by cosine similarity."""
        scored = [
            (self.cosine_similarity(query, c), c)
            for c in candidates
            if c.strategy_id != query.strategy_id
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]


__all__ = ["EmbedderConfig", "TraderEmbedder", "TraderEmbedding"]
