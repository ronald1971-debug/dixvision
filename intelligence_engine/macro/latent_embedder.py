"""MAC-03 — deterministic offline latent embeddings.

Produces fixed-dimensional embeddings from macro feature vectors using
a deterministic linear projection (fixed seed + checkpoint, ledgered).
Pure. INV-15. B1 compliant.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass

__all__ = ["LatentEmbedding", "LatentEmbedder"]


@dataclass(frozen=True, slots=True)
class LatentEmbedding:
    feature_id: str
    ts_ns: int
    embedding: tuple[float, ...]
    dim: int
    seed: int
    digest: str   # BLAKE2b-128 hex of (feature_id, embedding)


class LatentEmbedder:
    """Deterministic linear projector for macro feature vectors.

    The projection matrix is generated once from ``seed`` and reused
    for all subsequent calls. Identical (seed, dim, features) → identical
    embedding (INV-15).
    """

    def __init__(self, seed: int = 42, dim: int = 64, input_dim: int = 16) -> None:
        self._seed = seed
        self._dim = dim
        self._input_dim = input_dim
        self._matrix = self._make_matrix(seed, dim, input_dim)

    @staticmethod
    def _make_matrix(seed: int, dim: int, input_dim: int) -> list[list[float]]:
        rng = random.Random(seed)
        return [[rng.gauss(0, 1) for _ in range(input_dim)] for _ in range(dim)]

    def embed(
        self,
        feature_id: str,
        ts_ns: int,
        features: list[float],
    ) -> LatentEmbedding:
        padded = (features + [0.0] * self._input_dim)[: self._input_dim]
        vec = tuple(
            sum(self._matrix[i][j] * padded[j] for j in range(self._input_dim))
            for i in range(self._dim)
        )
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vec = tuple(v / norm for v in vec)

        canonical = json.dumps(
            {"feature_id": feature_id, "embedding": list(vec)},
            sort_keys=True, separators=(",", ":"),
        )
        digest = hashlib.blake2b(canonical.encode(), digest_size=16).hexdigest()
        return LatentEmbedding(
            feature_id=feature_id, ts_ns=ts_ns,
            embedding=vec, dim=self._dim, seed=self._seed, digest=digest,
        )
