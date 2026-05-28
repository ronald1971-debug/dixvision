"""Trader clustering (BUILD-DIRECTIVE §15 — TIS module 11).

Clusters traders by philosophy, behavior, and performance similarity.
Clusters inform the meta-controller's allocation decisions — instead
of tracking 5000+ individual traders, Indira tracks ~30 clusters and
allocates at the cluster level.

Clustering dimensions:
- Philosophy vector similarity (worldview, horizon, risk)
- Behavioral consistency patterns
- Regime-specific performance correlation
- Strategy atom overlap
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TraderCluster:
    """A cluster of traders with similar characteristics."""

    cluster_id: str
    name: str
    centroid: tuple[float, ...]  # cluster center in embedding space
    member_ids: tuple[str, ...]
    dominant_archetype: str
    dominant_regime: str
    avg_reliability: float
    avg_credibility: float
    cluster_size: int


class TraderClustering:
    """Clusters traders by multi-dimensional similarity.

    Uses simple k-means-style clustering on philosophy vectors +
    behavioral features. The number of clusters adapts based on
    data volume (target: ~30 stable clusters).
    """

    def __init__(self, *, target_clusters: int = 30, min_cluster_size: int = 3) -> None:
        self._target_clusters = target_clusters
        self._min_cluster_size = min_cluster_size
        self._assignments: dict[str, str] = {}  # trader_id → cluster_id
        self._clusters: dict[str, TraderCluster] = {}

    def assign(
        self,
        *,
        trader_id: str,
        embedding: tuple[float, ...],
        archetype: str = "",
        reliability: float = 0.5,
        credibility: float = 0.5,
    ) -> str:
        """Assign a trader to the nearest cluster (or create one)."""
        if not self._clusters:
            cluster_id = "cluster_0"
            self._clusters[cluster_id] = TraderCluster(
                cluster_id=cluster_id,
                name=f"Cluster-{archetype or 'mixed'}",
                centroid=embedding,
                member_ids=(trader_id,),
                dominant_archetype=archetype,
                dominant_regime="ALL",
                avg_reliability=reliability,
                avg_credibility=credibility,
                cluster_size=1,
            )
            self._assignments[trader_id] = cluster_id
            return cluster_id

        # Find nearest cluster by euclidean distance
        best_cluster = ""
        best_dist = float("inf")
        for cid, cluster in self._clusters.items():
            dist = self._euclidean(embedding, cluster.centroid)
            if dist < best_dist:
                best_dist = dist
                best_cluster = cid

        # If too far and under target, create new cluster
        if best_dist > 2.0 and len(self._clusters) < self._target_clusters:
            cluster_id = f"cluster_{len(self._clusters)}"
            self._clusters[cluster_id] = TraderCluster(
                cluster_id=cluster_id,
                name=f"Cluster-{archetype or 'mixed'}-{len(self._clusters)}",
                centroid=embedding,
                member_ids=(trader_id,),
                dominant_archetype=archetype,
                dominant_regime="ALL",
                avg_reliability=reliability,
                avg_credibility=credibility,
                cluster_size=1,
            )
            self._assignments[trader_id] = cluster_id
            return cluster_id

        # Assign to nearest existing cluster
        self._assignments[trader_id] = best_cluster
        # Update cluster (immutable, so rebuild)
        old = self._clusters[best_cluster]
        new_members = old.member_ids + (trader_id,)
        new_size = old.cluster_size + 1
        # Simple centroid update
        new_centroid = tuple(
            (old.centroid[i] * old.cluster_size + embedding[i]) / new_size
            if i < len(embedding) and i < len(old.centroid)
            else 0.0
            for i in range(max(len(old.centroid), len(embedding)))
        )
        self._clusters[best_cluster] = TraderCluster(
            cluster_id=best_cluster,
            name=old.name,
            centroid=new_centroid,
            member_ids=new_members,
            dominant_archetype=old.dominant_archetype,
            dominant_regime=old.dominant_regime,
            avg_reliability=(old.avg_reliability * old.cluster_size + reliability) / new_size,
            avg_credibility=(old.avg_credibility * old.cluster_size + credibility) / new_size,
            cluster_size=new_size,
        )
        return best_cluster

    def get_cluster(self, cluster_id: str) -> TraderCluster | None:
        """Get cluster by ID."""
        return self._clusters.get(cluster_id)

    def get_trader_cluster(self, trader_id: str) -> str | None:
        """Get cluster assignment for a trader."""
        return self._assignments.get(trader_id)

    def get_all_clusters(self) -> list[TraderCluster]:
        """Get all clusters."""
        return list(self._clusters.values())

    @property
    def cluster_count(self) -> int:
        """Number of active clusters."""
        return len(self._clusters)

    @staticmethod
    def _euclidean(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        """Euclidean distance between two vectors."""
        min_len = min(len(a), len(b))
        return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(min_len)))
