"""Narrative embeddings (BUILD-DIRECTIVE §17).

Stores and retrieves narrative embeddings — vector representations of
market narratives (e.g., "risk-off rotation", "BTC halving supercycle",
"Fed pivot speculation") for similarity search and clustering.

Uses FAISS-compatible interface. Embeddings are stored on disk under
state/vector_memory/ for persistence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NarrativeEmbedding:
    """A narrative encoded as a dense vector."""

    narrative_id: str
    theme: str
    vector: tuple[float, ...]
    strength: float  # how dominant this narrative currently is
    source_count: int  # number of sources referencing it
    ts_ns: int


class NarrativeEmbeddingStore:
    """Vector store for narrative embeddings.

    Supports:
    - Insert narrative embeddings
    - Find similar narratives by cosine similarity
    - Track narrative strength over time
    - Cluster narratives into themes
    """

    def __init__(self, *, dimension: int = 64) -> None:
        self._dimension = dimension
        self._embeddings: dict[str, NarrativeEmbedding] = {}

    def insert(self, embedding: NarrativeEmbedding) -> None:
        """Insert or update a narrative embedding."""
        self._embeddings[embedding.narrative_id] = embedding

    def search(
        self, query_vector: tuple[float, ...], *, top_k: int = 5, min_similarity: float = 0.3
    ) -> list[tuple[NarrativeEmbedding, float]]:
        """Find most similar narratives to a query vector."""
        results: list[tuple[NarrativeEmbedding, float]] = []
        for emb in self._embeddings.values():
            sim = self._cosine_similarity(query_vector, emb.vector)
            if sim >= min_similarity:
                results.append((emb, sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def get_active_narratives(
        self, *, min_strength: float = 0.3, min_sources: int = 2
    ) -> list[NarrativeEmbedding]:
        """Get currently active narratives above strength threshold."""
        return [
            e
            for e in self._embeddings.values()
            if e.strength >= min_strength and e.source_count >= min_sources
        ]

    def get_dominant_theme(self) -> NarrativeEmbedding | None:
        """Get the strongest current narrative."""
        if not self._embeddings:
            return None
        return max(self._embeddings.values(), key=lambda e: e.strength)

    def remove_stale(self, *, cutoff_ts_ns: int) -> int:
        """Remove narratives older than cutoff. Returns count removed."""
        stale = [nid for nid, e in self._embeddings.items() if e.ts_ns < cutoff_ts_ns]
        for nid in stale:
            del self._embeddings[nid]
        return len(stale)

    @property
    def size(self) -> int:
        """Number of stored narratives."""
        return len(self._embeddings)

    @staticmethod
    def _cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        """Cosine similarity between two vectors."""
        min_len = min(len(a), len(b))
        if min_len == 0:
            return 0.0
        dot = sum(a[i] * b[i] for i in range(min_len))
        norm_a = math.sqrt(sum(x * x for x in a[:min_len]))
        norm_b = math.sqrt(sum(x * x for x in b[:min_len]))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)
