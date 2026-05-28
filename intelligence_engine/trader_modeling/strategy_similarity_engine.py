"""Strategy similarity engine (BUILD-DIRECTIVE §15 — TIS module 12).

Computes similarity between strategy atoms, composed strategies, and
trader approaches. Used for:
- Deduplication (two atoms that do the same thing)
- Diversity enforcement (composition must be diverse)
- Correlation detection (atoms that always win/lose together)
- Novelty scoring (how different is a new atom from existing ones)
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SimilarityResult:
    """Result of a similarity comparison."""

    item_a: str
    item_b: str
    cosine_similarity: float  # -1 to 1
    overlap_score: float  # 0 to 1 (regime/condition overlap)
    correlation: float  # -1 to 1 (performance correlation)
    is_duplicate: bool  # above dedup threshold
    is_complementary: bool  # negatively correlated (good for diversity)


class StrategySimilarityEngine:
    """Computes similarity between strategy atoms and composed strategies.

    Key use cases:
    1. Dedup: Don't compose two atoms that do the same thing
    2. Diversity: Ensure compositions have diverse signal sources
    3. Correlation: Detect atoms that always fail together (shared risk)
    4. Novelty: Score how novel a new discovery is
    """

    def __init__(
        self,
        *,
        dedup_threshold: float = 0.92,
        complementary_threshold: float = -0.3,
    ) -> None:
        self._dedup_threshold = dedup_threshold
        self._complementary_threshold = complementary_threshold
        self._embeddings: dict[str, tuple[float, ...]] = {}
        self._performance_history: dict[str, list[float]] = {}

    def register_embedding(self, item_id: str, embedding: tuple[float, ...]) -> None:
        """Register an item's embedding for similarity computation."""
        self._embeddings[item_id] = embedding

    def record_performance(self, item_id: str, outcome: float) -> None:
        """Record a performance outcome for correlation computation."""
        self._performance_history.setdefault(item_id, []).append(outcome)

    def compare(self, item_a: str, item_b: str) -> SimilarityResult:
        """Compare two items for similarity."""
        emb_a = self._embeddings.get(item_a, ())
        emb_b = self._embeddings.get(item_b, ())

        cos_sim = self._cosine_similarity(emb_a, emb_b) if emb_a and emb_b else 0.0

        # Performance correlation
        perf_a = self._performance_history.get(item_a, [])
        perf_b = self._performance_history.get(item_b, [])
        correlation = self._pearson_correlation(perf_a, perf_b)

        # Overlap (using embedding dimensions as proxy for regime coverage)
        overlap = self._overlap_score(emb_a, emb_b)

        return SimilarityResult(
            item_a=item_a,
            item_b=item_b,
            cosine_similarity=cos_sim,
            overlap_score=overlap,
            correlation=correlation,
            is_duplicate=cos_sim >= self._dedup_threshold,
            is_complementary=correlation <= self._complementary_threshold,
        )

    def find_duplicates(self, item_id: str, *, threshold: float | None = None) -> list[str]:
        """Find items that are near-duplicates of the given item."""
        thresh = threshold if threshold is not None else self._dedup_threshold
        emb = self._embeddings.get(item_id)
        if not emb:
            return []
        dupes: list[str] = []
        for other_id, other_emb in self._embeddings.items():
            if other_id == item_id:
                continue
            sim = self._cosine_similarity(emb, other_emb)
            if sim >= thresh:
                dupes.append(other_id)
        return dupes

    def novelty_score(self, embedding: tuple[float, ...]) -> float:
        """Score how novel an embedding is relative to existing items.

        Returns 1.0 if completely novel, 0.0 if identical to existing.
        """
        if not self._embeddings:
            return 1.0
        max_sim = max(
            self._cosine_similarity(embedding, existing) for existing in self._embeddings.values()
        )
        return 1.0 - max(0.0, max_sim)

    def diversity_score(self, item_ids: list[str]) -> float:
        """Score the diversity of a set of items (0=all same, 1=all different)."""
        if len(item_ids) <= 1:
            return 1.0
        similarities: list[float] = []
        for i in range(len(item_ids)):
            for j in range(i + 1, len(item_ids)):
                emb_a = self._embeddings.get(item_ids[i], ())
                emb_b = self._embeddings.get(item_ids[j], ())
                if emb_a and emb_b:
                    similarities.append(self._cosine_similarity(emb_a, emb_b))
        if not similarities:
            return 0.5
        avg_sim = sum(similarities) / len(similarities)
        return 1.0 - max(0.0, avg_sim)

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

    @staticmethod
    def _pearson_correlation(a: list[float], b: list[float]) -> float:
        """Pearson correlation between two series."""
        n = min(len(a), len(b))
        if n < 3:
            return 0.0
        mean_a = sum(a[:n]) / n
        mean_b = sum(b[:n]) / n
        cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
        var_a = sum((a[i] - mean_a) ** 2 for i in range(n))
        var_b = sum((b[i] - mean_b) ** 2 for i in range(n))
        denom = math.sqrt(var_a * var_b)
        if denom == 0.0:
            return 0.0
        return cov / denom

    @staticmethod
    def _overlap_score(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        """Overlap score based on non-zero dimension coverage."""
        min_len = min(len(a), len(b))
        if min_len == 0:
            return 0.0
        both_active = sum(1 for i in range(min_len) if a[i] != 0 and b[i] != 0)
        either_active = sum(1 for i in range(min_len) if a[i] != 0 or b[i] != 0)
        if either_active == 0:
            return 0.0
        return both_active / either_active
