"""state/memory_tensor/meta_memory.py
DIX VISION v42.2 — Meta Memory Store

Stores meta-level memories: summaries of learning episodes, strategy
performance patterns, and system behavioural observations that inform
future adaptation. Distinct from episodic (raw experiences) and
procedural (action sequences) — meta memories capture *what was learned*.

Thread-safe. Bounded with recency-weighted eviction. INV-15 compliant.
"""

from __future__ import annotations

import hashlib
import threading
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class MetaMemoryKind(StrEnum):
    STRATEGY_INSIGHT = "STRATEGY_INSIGHT"
    REGIME_PATTERN = "REGIME_PATTERN"
    FAILURE_MODE = "FAILURE_MODE"
    CALIBRATION_UPDATE = "CALIBRATION_UPDATE"
    ARCHETYPE_SUMMARY = "ARCHETYPE_SUMMARY"
    SYSTEM_BEHAVIOR = "SYSTEM_BEHAVIOR"


@dataclass(frozen=True, slots=True)
class MetaMemoryRecord:
    """One meta-memory entry."""
    record_id: str
    kind: MetaMemoryKind
    subject: str            # what this memory is about (e.g. strategy_id, regime)
    summary: str            # human-readable summary
    confidence: float       # [0, 1]
    supporting_evidence: tuple[str, ...]   # record IDs or event IDs
    tags: tuple[str, ...]
    ts_ns: int
    meta: dict[str, str]


class MetaMemoryStore:
    """
    Bounded meta-memory store with tag-based retrieval.

    Thread-safe. Stores at most ``capacity`` records; oldest are evicted.
    """

    def __init__(self, capacity: int = 500) -> None:
        self._capacity = capacity
        self._lock = threading.Lock()
        self._records: deque[MetaMemoryRecord] = deque(maxlen=capacity)
        # subject → list of record_ids for fast lookup
        self._subject_index: dict[str, list[str]] = {}
        self._kind_index: dict[MetaMemoryKind, list[str]] = {}

    def store(self, record: MetaMemoryRecord) -> None:
        with self._lock:
            self._records.append(record)
            self._subject_index.setdefault(record.subject, []).append(record.record_id)
            self._kind_index.setdefault(record.kind, []).append(record.record_id)

    def query_by_subject(
        self,
        subject: str,
        kind: MetaMemoryKind | None = None,
        min_confidence: float = 0.0,
    ) -> list[MetaMemoryRecord]:
        """Return records for a subject, optionally filtered by kind and confidence."""
        with self._lock:
            all_recs = {r.record_id: r for r in self._records}
            ids = self._subject_index.get(subject, [])
            results = [all_recs[rid] for rid in ids if rid in all_recs]
        if kind is not None:
            results = [r for r in results if r.kind == kind]
        if min_confidence > 0.0:
            results = [r for r in results if r.confidence >= min_confidence]
        return sorted(results, key=lambda r: r.ts_ns, reverse=True)

    def query_by_kind(
        self,
        kind: MetaMemoryKind,
        top_k: int = 20,
    ) -> list[MetaMemoryRecord]:
        """Return the most recent records of a given kind."""
        with self._lock:
            all_recs = {r.record_id: r for r in self._records}
            ids = self._kind_index.get(kind, [])
            results = [all_recs[rid] for rid in ids if rid in all_recs]
        results.sort(key=lambda r: r.ts_ns, reverse=True)
        return results[:top_k]

    def best_insight(
        self,
        subject: str,
        kind: MetaMemoryKind | None = None,
    ) -> MetaMemoryRecord | None:
        """Return the highest-confidence memory for a subject."""
        results = self.query_by_subject(subject, kind)
        if not results:
            return None
        return max(results, key=lambda r: r.confidence)

    def tag_search(self, tag: str) -> list[MetaMemoryRecord]:
        """Return all records that have a given tag."""
        with self._lock:
            return [r for r in self._records if tag in r.tags]

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "capacity": self._capacity,
                "size": len(self._records),
                "subjects": len(self._subject_index),
                "kinds": {k.value: len(v) for k, v in self._kind_index.items()},
            }


# Singleton factory
_instance: MetaMemoryStore | None = None
_lock = threading.Lock()


def get_meta_memory() -> MetaMemoryStore:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = MetaMemoryStore()
    return _instance


__all__ = [
    "MetaMemoryKind",
    "MetaMemoryRecord",
    "MetaMemoryStore",
    "get_meta_memory",
]
