"""state/memory_tensor/procedural.py
DIX VISION v42.2 — Procedural Memory Store

Stores and retrieves procedural knowledge: action-outcome mappings
that encode *how to do* things rather than *what happened* (episodic)
or *what something means* (semantic). Used by the learning engine
to store strategy execution procedures.

Thread-safe. Bounded capacity with LRU eviction. INV-15 compliant.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProceduralRecord:
    """One procedural memory entry."""
    record_id: str
    procedure_name: str     # e.g. "trend_entry", "drawdown_exit"
    context_key: str        # hash of the context that activates this
    action_sequence: tuple[str, ...]
    outcome_score: float    # historical success score [0, 1]
    execution_count: int
    last_outcome: str       # description of the most recent outcome
    ts_ns: int


def _context_key(context: dict[str, Any]) -> str:
    """Deterministic hash of a context dict."""
    canonical = "|".join(f"{k}={v}" for k, v in sorted(context.items()))
    return hashlib.md5(canonical.encode()).hexdigest()[:16]


class ProceduralMemoryStore:
    """
    Bounded LRU store for procedural knowledge.

    Thread-safe. Evicts least-recently-used entries when capacity
    is exceeded.
    """

    def __init__(self, capacity: int = 1000) -> None:
        self._capacity = capacity
        self._lock = threading.Lock()
        # OrderedDict for LRU: key → ProceduralRecord
        self._store: OrderedDict[str, ProceduralRecord] = OrderedDict()

    def store(self, record: ProceduralRecord) -> None:
        with self._lock:
            if record.record_id in self._store:
                self._store.move_to_end(record.record_id)
            self._store[record.record_id] = record
            if len(self._store) > self._capacity:
                self._store.popitem(last=False)

    def lookup(self, procedure_name: str, context: dict[str, Any]) -> ProceduralRecord | None:
        """Find the best matching procedural record for a context."""
        ctx_key = _context_key(context)
        with self._lock:
            for rec in reversed(list(self._store.values())):
                if rec.procedure_name == procedure_name and rec.context_key == ctx_key:
                    self._store.move_to_end(rec.record_id)
                    return rec
        return None

    def all_for_procedure(self, procedure_name: str) -> list[ProceduralRecord]:
        """Return all records for a given procedure, sorted by outcome_score desc."""
        with self._lock:
            records = [r for r in self._store.values() if r.procedure_name == procedure_name]
        return sorted(records, key=lambda r: r.outcome_score, reverse=True)

    def update_outcome(
        self,
        record_id: str,
        new_outcome_score: float,
        last_outcome: str,
        ts_ns: int,
    ) -> ProceduralRecord | None:
        """Update the outcome score for a record."""
        with self._lock:
            rec = self._store.get(record_id)
            if rec is None:
                return None
            updated = ProceduralRecord(
                record_id=rec.record_id,
                procedure_name=rec.procedure_name,
                context_key=rec.context_key,
                action_sequence=rec.action_sequence,
                outcome_score=new_outcome_score,
                execution_count=rec.execution_count + 1,
                last_outcome=last_outcome,
                ts_ns=ts_ns,
            )
            self._store[record_id] = updated
            self._store.move_to_end(record_id)
        return updated

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "capacity": self._capacity,
                "size": len(self._store),
                "procedures": list({r.procedure_name for r in self._store.values()}),
            }


# Singleton factory
_instance: ProceduralMemoryStore | None = None
_lock = threading.Lock()


def get_procedural_memory() -> ProceduralMemoryStore:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ProceduralMemoryStore()
    return _instance


__all__ = [
    "ProceduralMemoryStore",
    "ProceduralRecord",
    "get_procedural_memory",
]
