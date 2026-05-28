"""Bridge: Qdrant adapter → learning_engine/vector_memory.

Wires the Qdrant OSS adapter as the backend for DIXVISION's vector
memory subsystem. Narrative, strategy, regime, and trader embeddings
stored and retrieved via Qdrant's semantic search.

The bridge maps DIXVISION memory domains to Qdrant collections and
provides a unified interface for all vector_memory modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from integrations.qdrant_adapter.memory import (
    MemoryDomain,
    QdrantMemoryAdapter,
    VectorPoint,
)
from system import time_source


@dataclass(frozen=True, slots=True)
class EmbeddingRecord:
    """A stored embedding with metadata."""

    record_id: str
    domain: str
    vector: tuple[float, ...]
    payload: dict[str, Any]
    score: float = 0.0
    ts_ns: int = 0


class QdrantMemoryBridge:
    """Bridge between Qdrant adapter and learning_engine/vector_memory.

    Provides:
    - Store narrative embeddings (market themes, macro regimes)
    - Store strategy embeddings (trader DNA, performance signatures)
    - Store regime embeddings (market state vectors)
    - Semantic similarity search across all domains
    - Temporal queries (embeddings within time range)

    Maps vector_memory domains to Qdrant collections:
    - narrative_embeddings → MemoryDomain.NARRATIVES
    - strategy_embeddings → MemoryDomain.STRATEGIES
    - market_regime_embeddings → MemoryDomain.REGIMES
    - trader_embeddings → MemoryDomain.TRADERS
    """

    def __init__(self, *, dimension: int = 64) -> None:
        self._adapter = QdrantMemoryAdapter()
        self._dimension = dimension
        self._initialized = False
        self._insert_count = 0

    def initialize(self) -> bool:
        """Connect to Qdrant and create collections."""
        connected = self._adapter.connect()
        if connected:
            for domain in MemoryDomain:
                self._adapter.create_collection(domain, vector_size=self._dimension)
            self._initialized = True
        return connected

    # --- Store embeddings ---

    def store_narrative(
        self,
        narrative_id: str,
        vector: tuple[float, ...],
        *,
        theme: str = "",
        strength: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Store a narrative embedding."""
        payload = {
            "theme": theme,
            "strength": strength,
            "ts_ns": time_source.wall_ns(),
            **(metadata or {}),
        }
        point = VectorPoint(
            point_id=narrative_id,
            vector=vector,
            payload=payload,
        )
        count = self._adapter.upsert(MemoryDomain.NARRATIVES, points=[point])
        self._insert_count += count
        return count > 0

    def store_strategy(
        self,
        strategy_id: str,
        vector: tuple[float, ...],
        *,
        trader_base: str = "",
        win_rate: float = 0.0,
        sharpe: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Store a strategy embedding."""
        payload = {
            "trader_base": trader_base,
            "win_rate": win_rate,
            "sharpe": sharpe,
            "ts_ns": time_source.wall_ns(),
            **(metadata or {}),
        }
        point = VectorPoint(
            point_id=strategy_id,
            vector=vector,
            payload=payload,
        )
        count = self._adapter.upsert(MemoryDomain.STRATEGIES, points=[point])
        self._insert_count += count
        return count > 0

    def store_regime(
        self,
        regime_id: str,
        vector: tuple[float, ...],
        *,
        regime_type: str = "",
        confidence: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Store a regime embedding."""
        payload = {
            "regime_type": regime_type,
            "confidence": confidence,
            "ts_ns": time_source.wall_ns(),
            **(metadata or {}),
        }
        point = VectorPoint(
            point_id=regime_id,
            vector=vector,
            payload=payload,
        )
        count = self._adapter.upsert(MemoryDomain.REGIMES, points=[point])
        self._insert_count += count
        return count > 0

    def store_trader(
        self,
        trader_id: str,
        vector: tuple[float, ...],
        *,
        archetype: str = "",
        group: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Store a trader embedding."""
        payload = {
            "archetype": archetype,
            "group": group,
            "ts_ns": time_source.wall_ns(),
            **(metadata or {}),
        }
        point = VectorPoint(
            point_id=trader_id,
            vector=vector,
            payload=payload,
        )
        count = self._adapter.upsert(MemoryDomain.TRADERS, points=[point])
        self._insert_count += count
        return count > 0

    # --- Search ---

    def find_similar_narratives(
        self,
        query_vector: tuple[float, ...],
        *,
        limit: int = 5,
        min_score: float = 0.3,
    ) -> list[EmbeddingRecord]:
        """Find narratives similar to a query vector."""
        return self._search(MemoryDomain.NARRATIVES, query_vector, limit, min_score)

    def find_similar_strategies(
        self,
        query_vector: tuple[float, ...],
        *,
        limit: int = 5,
        min_score: float = 0.3,
    ) -> list[EmbeddingRecord]:
        """Find strategies similar to a query vector."""
        return self._search(MemoryDomain.STRATEGIES, query_vector, limit, min_score)

    def find_similar_regimes(
        self,
        query_vector: tuple[float, ...],
        *,
        limit: int = 5,
        min_score: float = 0.3,
    ) -> list[EmbeddingRecord]:
        """Find regimes similar to a query vector."""
        return self._search(MemoryDomain.REGIMES, query_vector, limit, min_score)

    def find_similar_traders(
        self,
        query_vector: tuple[float, ...],
        *,
        limit: int = 5,
        min_score: float = 0.3,
    ) -> list[EmbeddingRecord]:
        """Find traders similar to a query vector."""
        return self._search(MemoryDomain.TRADERS, query_vector, limit, min_score)

    # --- Info ---

    @property
    def total_embeddings(self) -> int:
        """Total embeddings stored across all domains."""
        return sum(self._adapter.count(domain) for domain in MemoryDomain)

    @property
    def insert_count(self) -> int:
        """Total insert operations."""
        return self._insert_count

    # --- Internal ---

    def _search(
        self,
        domain: MemoryDomain,
        query_vector: tuple[float, ...],
        limit: int,
        min_score: float,
    ) -> list[EmbeddingRecord]:
        """Run similarity search in a domain."""
        results = self._adapter.search(
            domain,
            query_vector=query_vector,
            limit=limit,
            score_threshold=min_score,
        )
        return [
            EmbeddingRecord(
                record_id=r.point_id,
                domain=domain.value,
                vector=(),
                payload=r.payload,
                score=r.score,
                ts_ns=r.payload.get("ts_ns", 0),
            )
            for r in results
        ]
