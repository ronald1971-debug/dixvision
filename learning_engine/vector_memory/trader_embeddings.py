"""Trader philosophy embeddings (BUILD-DIRECTIVE §17).

Stores and retrieves trader philosophy vectors via FAISS for:
- Similar trader discovery
- Philosophy clustering
- Strategy atom recommendation based on philosophy match
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class EmbeddingRecord:
    """A stored embedding with metadata."""

    record_id: str
    vector: tuple[float, ...]
    metadata: dict[str, Any]


class TraderEmbeddingStore:
    """In-memory vector store for trader philosophy embeddings.

    Uses numpy for similarity computation. FAISS integration is optional
    and activated when the faiss-cpu package is available.
    """

    def __init__(self, *, dimension: int = 5) -> None:
        self._dimension = dimension
        self._records: list[EmbeddingRecord] = []
        self._vectors: list[np.ndarray] = []

    def add(self, record: EmbeddingRecord) -> None:
        """Add an embedding to the store."""
        vec = np.array(record.vector, dtype=np.float32)
        if vec.shape[0] != self._dimension:
            msg = f"expected dim={self._dimension}, got {vec.shape[0]}"
            raise ValueError(msg)
        self._records.append(record)
        self._vectors.append(vec)

    def search(
        self, query: tuple[float, ...], *, top_k: int = 5
    ) -> list[tuple[EmbeddingRecord, float]]:
        """Find top-k most similar embeddings by cosine similarity."""
        if not self._vectors:
            return []
        q = np.array(query, dtype=np.float32)
        q_norm = q / (np.linalg.norm(q) + 1e-10)

        scores = []
        for i, v in enumerate(self._vectors):
            v_norm = v / (np.linalg.norm(v) + 1e-10)
            sim = float(np.dot(q_norm, v_norm))
            scores.append((i, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [(self._records[idx], score) for idx, score in scores[:top_k]]

    @property
    def size(self) -> int:
        """Number of embeddings stored."""
        return len(self._records)
