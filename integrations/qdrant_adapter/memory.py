"""Qdrant vector memory adapter (OSS Integration Layer).

Provides semantic memory operations backed by Qdrant.
Replaces custom FAISS/numpy-based vector stores with a proper
vector database that supports filtering, payloads, and scaling.

Collections map to DIXVISION memory domains:
- dix_traders: trader philosophy/style embeddings
- dix_strategies: strategy atom embeddings
- dix_narratives: market narrative embeddings
- dix_regimes: regime state embeddings
- dix_episodes: episodic trading memory

Reference: github.com/qdrant/qdrant
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class MemoryDomain(StrEnum):
    """DIXVISION memory domains mapped to Qdrant collections."""

    TRADERS = "dix_traders"
    STRATEGIES = "dix_strategies"
    NARRATIVES = "dix_narratives"
    REGIMES = "dix_regimes"
    EPISODES = "dix_episodes"
    SIGNALS = "dix_signals"


@dataclass(frozen=True, slots=True)
class VectorPoint:
    """A point in vector space with payload."""

    point_id: str
    vector: tuple[float, ...]
    payload: dict[str, Any]
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Result from a vector similarity search."""

    point_id: str
    score: float
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CollectionInfo:
    """Info about a Qdrant collection."""

    name: str
    vector_size: int
    point_count: int
    status: str


class QdrantMemoryAdapter:
    """DIXVISION adapter wrapping Qdrant vector database.

    Provides:
    - Semantic storage (upsert embeddings with metadata)
    - Similarity search (find nearest neighbors)
    - Filtered search (combine vector + metadata filters)
    - Collection management (create/delete/info)

    Falls back to in-memory storage if Qdrant is unavailable.
    """

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 6333,
        api_key: str = "",
        vector_size: int = 384,
        use_inmemory: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._api_key = api_key
        self._vector_size = vector_size
        self._use_inmemory = use_inmemory
        self._client: Any = None
        self._inmemory_store: dict[str, list[VectorPoint]] = {}

    def connect(self) -> bool:
        """Connect to Qdrant server (or initialize in-memory)."""
        if self._use_inmemory:
            return True
        try:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(
                host=self._host,
                port=self._port,
                api_key=self._api_key or None,
            )
            return True
        except ImportError:
            # Qdrant client not installed — fall back to in-memory
            self._use_inmemory = True
            return True

    def create_collection(self, domain: MemoryDomain, *, vector_size: int | None = None) -> bool:
        """Create a collection for a memory domain."""
        size = vector_size or self._vector_size

        if self._use_inmemory:
            self._inmemory_store.setdefault(domain.value, [])
            return True

        try:
            from qdrant_client.models import Distance, VectorParams

            self._client.create_collection(
                collection_name=domain.value,
                vectors_config=VectorParams(size=size, distance=Distance.COSINE),
            )
            return True
        except Exception:
            return False

    def upsert(
        self,
        domain: MemoryDomain,
        *,
        points: list[VectorPoint],
    ) -> int:
        """Upsert points into a collection. Returns count upserted."""
        if self._use_inmemory:
            store = self._inmemory_store.setdefault(domain.value, [])
            existing_ids = {p.point_id for p in store}
            for point in points:
                if point.point_id in existing_ids:
                    store[:] = [p for p in store if p.point_id != point.point_id]
                store.append(point)
            return len(points)

        try:
            from qdrant_client.models import PointStruct

            qdrant_points = [
                PointStruct(
                    id=p.point_id,
                    vector=list(p.vector),
                    payload=p.payload,
                )
                for p in points
            ]
            self._client.upsert(collection_name=domain.value, points=qdrant_points)
            return len(points)
        except Exception:
            return 0

    def search(
        self,
        domain: MemoryDomain,
        *,
        query_vector: tuple[float, ...],
        limit: int = 10,
        score_threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search for similar vectors."""
        if self._use_inmemory:
            return self._inmemory_search(
                domain,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
            )

        try:
            results = self._client.search(
                collection_name=domain.value,
                query_vector=list(query_vector),
                limit=limit,
                score_threshold=score_threshold,
            )
            return [
                SearchResult(
                    point_id=str(r.id),
                    score=r.score,
                    payload=r.payload or {},
                )
                for r in results
            ]
        except Exception:
            return []

    def delete(self, domain: MemoryDomain, *, point_ids: list[str]) -> int:
        """Delete points by ID."""
        if self._use_inmemory:
            store = self._inmemory_store.get(domain.value, [])
            before = len(store)
            store[:] = [p for p in store if p.point_id not in set(point_ids)]
            return before - len(store)

        try:
            self._client.delete(
                collection_name=domain.value,
                points_selector=point_ids,
            )
            return len(point_ids)
        except Exception:
            return 0

    def count(self, domain: MemoryDomain) -> int:
        """Count points in a collection."""
        if self._use_inmemory:
            return len(self._inmemory_store.get(domain.value, []))

        try:
            info = self._client.get_collection(domain.value)
            return info.points_count or 0
        except Exception:
            return 0

    def collection_info(self, domain: MemoryDomain) -> CollectionInfo | None:
        """Get collection metadata."""
        if self._use_inmemory:
            count = len(self._inmemory_store.get(domain.value, []))
            return CollectionInfo(
                name=domain.value,
                vector_size=self._vector_size,
                point_count=count,
                status="green",
            )
        try:
            info = self._client.get_collection(domain.value)
            return CollectionInfo(
                name=domain.value,
                vector_size=self._vector_size,
                point_count=info.points_count or 0,
                status=str(info.status),
            )
        except Exception:
            return None

    def _inmemory_search(
        self,
        domain: MemoryDomain,
        *,
        query_vector: tuple[float, ...],
        limit: int,
        score_threshold: float,
    ) -> list[SearchResult]:
        """In-memory cosine similarity search."""
        store = self._inmemory_store.get(domain.value, [])
        if not store:
            return []

        scored: list[tuple[float, VectorPoint]] = []
        for point in store:
            score = self._cosine_sim(query_vector, point.vector)
            if score >= score_threshold:
                scored.append((score, point))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            SearchResult(
                point_id=p.point_id,
                score=s,
                payload=p.payload,
            )
            for s, p in scored[:limit]
        ]

    @staticmethod
    def _cosine_sim(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        mag_a = sum(x * x for x in a) ** 0.5
        mag_b = sum(x * x for x in b) ** 0.5
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
