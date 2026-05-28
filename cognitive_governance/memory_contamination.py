"""
cognitive_governance/memory_contamination.py
DIX VISION v42.2 — Memory Contamination Detector

Watches vector memory stores for two contamination patterns:

  1. SEMANTIC DRIFT — embeddings of a stable concept drift faster than
     expected (measured as the rolling 1-hour mean cosine distance
     between a concept's current centroid and its 24h-ago centroid).
     Normal drift is < 0.05/hour. Warning > 0.15. Critical > 0.30.

  2. EMBEDDING COLLAPSE — the standard deviation of cosine distances
     across a store's embedding space falls below COLLAPSE_THRESHOLD.
     This means the store is losing discriminating power — all concepts
     start looking the same. Warning < 0.12. Critical < 0.05.

Neither pattern is directly observable from raw embeddings without
baseline comparison. This guard maintains a rolling centroid history
per named store and computes drift against it.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from typing import Any

from core.contracts.cognitive_governance import (
    CognitiveSeverity,
    CognitiveViolationKind,
    MemoryContaminationReport,
)
from state.ledger.event_store import append_event

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DRIFT_WARNING = 0.15
DRIFT_CRITICAL = 0.30
COLLAPSE_WARNING = 0.12
COLLAPSE_CRITICAL = 0.05

# How many centroid snapshots to keep per concept (rolling 24h at 1h cadence → 24)
_CENTROID_HISTORY_LEN = 24
# Minimum number of embeddings needed before collapse detection is reliable
_MIN_EMBEDDINGS_FOR_COLLAPSE = 5
# 1 hour in nanoseconds
_ONE_HOUR_NS = 3_600_000_000_000


class MemoryContaminationDetector:
    """
    Tracks vector store health by maintaining per-concept centroid histories
    and computing semantic drift and embedding collapse scores.
    """

    def __init__(self) -> None:
        # store_name → concept_id → deque of (ts_ns, centroid: list[float])
        self._centroids: dict[str, dict[str, deque[tuple[int, list[float]]]]] = {}
        # store_name → deque of current embeddings (for collapse detection)
        self._recent_embeddings: dict[str, deque[list[float]]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_embedding(
        self,
        store_name: str,
        concept_id: str,
        embedding: list[float],
        ts_ns: int,
    ) -> None:
        """
        Register a new embedding for a concept in a named store.

        Maintains a rolling centroid history and a recent-embedding window
        for collapse detection.
        """
        with self._lock:
            # Initialise per-store structures
            if store_name not in self._centroids:
                self._centroids[store_name] = {}
                self._recent_embeddings[store_name] = deque(maxlen=200)

            self._recent_embeddings[store_name].append(embedding)

            hist = self._centroids[store_name].setdefault(
                concept_id, deque(maxlen=_CENTROID_HISTORY_LEN)
            )

            # Compute new centroid as mean of this embedding and last centroid
            if hist:
                _, prev_centroid = hist[-1]
                new_centroid = self._blend_centroid(prev_centroid, embedding, alpha=0.1)
            else:
                new_centroid = list(embedding)

            hist.append((ts_ns, new_centroid))

    def scan_store(self, store_name: str, ts_ns: int) -> MemoryContaminationReport:
        """
        Run contamination scan for the named store.

        Returns a MemoryContaminationReport with contamination score, drift
        rate, anomalous cluster count, severity and violation kinds.
        Emits COGOV_MEMORY_CONTAMINATION to the governance ledger if any
        violations are detected.
        """
        with self._lock:
            centroids = self._centroids.get(store_name, {})
            recent = list(self._recent_embeddings.get(store_name, deque()))

        violations: list[CognitiveViolationKind] = []
        severity = CognitiveSeverity.INFO
        anomalous_clusters = 0
        drift_rates: list[float] = []

        # Check semantic drift per concept
        for concept_id, hist in centroids.items():
            if len(hist) < 2:
                continue
            drift_rate = self._compute_drift_rate(hist, ts_ns)
            drift_rates.append(drift_rate)
            if drift_rate >= DRIFT_CRITICAL:
                anomalous_clusters += 1
            elif drift_rate >= DRIFT_WARNING:
                anomalous_clusters += 1

        # Overall drift rate: max over all concepts
        overall_drift = max(drift_rates) if drift_rates else 0.0

        if overall_drift >= DRIFT_CRITICAL:
            violations.append(CognitiveViolationKind.MEMORY_CONTAMINATION)
            severity = CognitiveSeverity.CRITICAL
        elif overall_drift >= DRIFT_WARNING:
            violations.append(CognitiveViolationKind.MEMORY_CONTAMINATION)
            if severity == CognitiveSeverity.INFO:
                severity = CognitiveSeverity.WARNING

        # Check embedding collapse
        if len(recent) >= _MIN_EMBEDDINGS_FOR_COLLAPSE:
            std_dev = self._compute_std_dev(recent)
            if std_dev <= COLLAPSE_CRITICAL:
                violations.append(CognitiveViolationKind.EMBEDDING_COLLAPSE)
                severity = CognitiveSeverity.CRITICAL
            elif std_dev <= COLLAPSE_WARNING:
                violations.append(CognitiveViolationKind.EMBEDDING_COLLAPSE)
                if severity == CognitiveSeverity.INFO:
                    severity = CognitiveSeverity.WARNING
        else:
            std_dev = 1.0  # not enough data; assume healthy

        # Contamination score: blend drift and collapse signals
        drift_score = min(overall_drift / DRIFT_CRITICAL, 1.0) if DRIFT_CRITICAL > 0 else 0.0
        collapse_score = max(0.0, 1.0 - (std_dev / COLLAPSE_WARNING)) if std_dev < COLLAPSE_WARNING else 0.0
        contamination_score = min(1.0, (drift_score * 0.6 + collapse_score * 0.4))

        passed = len(violations) == 0
        detail_parts = []
        if overall_drift >= DRIFT_WARNING:
            detail_parts.append(f"drift_rate={overall_drift:.4f}/hr, {anomalous_clusters} anomalous concept(s)")
        if std_dev <= COLLAPSE_WARNING:
            detail_parts.append(f"embedding_std_dev={std_dev:.4f} below collapse threshold")
        detail = "; ".join(detail_parts) if detail_parts else "OK"

        report = MemoryContaminationReport(
            ts_ns=ts_ns,
            store_name=store_name,
            passed=passed,
            contamination_score=contamination_score,
            drift_rate_per_hour=overall_drift,
            anomalous_clusters=anomalous_clusters,
            severity=severity,
            violations=tuple(violations),
            detail=detail,
        )

        if not passed:
            append_event(
                "GOVERNANCE",
                "COGOV_MEMORY_CONTAMINATION",
                "cognitive_governance.memory_contamination",
                {
                    "store_name": store_name,
                    "passed": passed,
                    "contamination_score": contamination_score,
                    "drift_rate_per_hour": overall_drift,
                    "anomalous_clusters": anomalous_clusters,
                    "severity": severity.value,
                    "violations": [v.value for v in violations],
                    "detail": detail,
                },
            )

        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_drift_rate(
        self, hist: deque[tuple[int, list[float]]], current_ts_ns: int
    ) -> float:
        """
        Compute the drift rate in cosine distance per hour.

        Compares the most recent centroid to the oldest centroid in the
        history window and divides by the elapsed time in hours.
        """
        items = list(hist)
        if len(items) < 2:
            return 0.0

        oldest_ts_ns, oldest_centroid = items[0]
        newest_ts_ns, newest_centroid = items[-1]

        elapsed_ns = newest_ts_ns - oldest_ts_ns
        if elapsed_ns <= 0:
            return 0.0

        dist = self._cosine_distance(oldest_centroid, newest_centroid)
        elapsed_hours = elapsed_ns / _ONE_HOUR_NS
        return dist / elapsed_hours if elapsed_hours > 0 else 0.0

    @staticmethod
    def _cosine_distance(a: list[float], b: list[float]) -> float:
        """Compute cosine distance = 1 - cosine_similarity."""
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 1.0
        cos_sim = dot / (norm_a * norm_b)
        # Clamp to [-1, 1] to guard against floating point drift
        cos_sim = max(-1.0, min(1.0, cos_sim))
        return 1.0 - cos_sim

    @staticmethod
    def _compute_std_dev(vectors: list[list[float]]) -> float:
        """
        Compute the mean pairwise cosine distance standard deviation.

        We sample the upper triangle of pairwise distances and compute std.
        For large stores we sample at most 200 pairs to keep it O(n) bounded.
        """
        n = len(vectors)
        if n < 2:
            return 1.0  # assume healthy when not enough data

        distances: list[float] = []
        max_pairs = 200
        count = 0

        for i in range(n):
            for j in range(i + 1, n):
                a = vectors[i]
                b = vectors[j]
                dot = sum(x * y for x, y in zip(a, b))
                norm_a = math.sqrt(sum(x * x for x in a))
                norm_b = math.sqrt(sum(x * x for x in b))
                if norm_a > 0 and norm_b > 0:
                    cos_sim = max(-1.0, min(1.0, dot / (norm_a * norm_b)))
                    distances.append(1.0 - cos_sim)
                count += 1
                if count >= max_pairs:
                    break
            if count >= max_pairs:
                break

        if not distances:
            return 1.0

        mean = sum(distances) / len(distances)
        variance = sum((d - mean) ** 2 for d in distances) / len(distances)
        return math.sqrt(variance)

    @staticmethod
    def _blend_centroid(old: list[float], new: list[float], alpha: float) -> list[float]:
        """Exponential moving average centroid update."""
        if len(old) != len(new):
            return list(new)
        return [(1 - alpha) * o + alpha * n for o, n in zip(old, new)]


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: MemoryContaminationDetector | None = None
_lock = threading.Lock()


def get_memory_contamination_detector() -> MemoryContaminationDetector:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = MemoryContaminationDetector()
    return _instance


__all__ = ["MemoryContaminationDetector", "get_memory_contamination_detector"]
