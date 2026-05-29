"""state.memory.stores.strategy — StrategyMemoryStore.

Records strategy proposals, mutations, fitness scores, and outcomes.
Enables INDIRA/DYON to recall which strategies worked, which failed,
and under which regimes.

No engine imports; no clock (INV-15); thread-safe.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from types import MappingProxyType
from typing import Any

from state.memory.contracts import MemoryKind, MemoryRecord

_logger   = logging.getLogger(__name__)
_MAX_SIZE = 2_000


class StrategyMemoryStore:
    """In-process ring-buffer store for strategy lifecycle events."""

    def __init__(self, max_size: int = _MAX_SIZE) -> None:
        self._max_size  = max_size
        self._lock      = threading.Lock()
        self._records:  deque[MemoryRecord] = deque(maxlen=max_size)
        self._by_id:    dict[str, MemoryRecord] = {}
        self._fitness:  dict[str, list[float]] = {}   # strategy_id → fitness history
        self._outcomes: dict[str, list[str]]   = {}   # strategy_id → outcome tags

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record_proposal(
        self,
        *,
        record_id:   str,
        strategy_id: str,
        ts_ns:       int,
        description: str,
        source:      str = "evolution_engine",
        tags:        frozenset[str] = frozenset(),
    ) -> MemoryRecord:
        rec = MemoryRecord(
            record_id  = record_id,
            kind       = MemoryKind.STRATEGY,
            ts_ns      = ts_ns,
            source     = source,
            summary    = f"PROPOSAL {strategy_id}: {description}",
            body       = MappingProxyType({"strategy_id": strategy_id, "event": "proposal"}),
            tags       = tags | frozenset(["proposal", strategy_id]),
        )
        self._store(rec)
        return rec

    def record_mutation(
        self,
        *,
        record_id:   str,
        strategy_id: str,
        ts_ns:       int,
        mutation:    str,
        fitness:     float,
        source:      str = "evolution_engine",
        tags:        frozenset[str] = frozenset(),
    ) -> MemoryRecord:
        rec = MemoryRecord(
            record_id  = record_id,
            kind       = MemoryKind.STRATEGY,
            ts_ns      = ts_ns,
            source     = source,
            summary    = f"MUTATION {strategy_id}: {mutation} fitness={fitness:.3f}",
            body       = MappingProxyType({
                "strategy_id": strategy_id,
                "mutation":    mutation,
                "fitness":     str(fitness),
                "event":       "mutation",
            }),
            tags       = tags | frozenset(["mutation", strategy_id]),
            confidence = max(0.0, min(1.0, fitness)),
        )
        with self._lock:
            self._fitness.setdefault(strategy_id, []).append(fitness)
        self._store(rec)
        return rec

    def record_outcome(
        self,
        *,
        record_id:   str,
        strategy_id: str,
        ts_ns:       int,
        outcome:     str,
        pnl:         float | None = None,
        source:      str = "evolution_engine",
        tags:        frozenset[str] = frozenset(),
    ) -> MemoryRecord:
        body: dict[str, str] = {"strategy_id": strategy_id, "outcome": outcome, "event": "outcome"}
        if pnl is not None:
            body["pnl"] = str(pnl)
        rec = MemoryRecord(
            record_id = record_id,
            kind      = MemoryKind.STRATEGY,
            ts_ns     = ts_ns,
            source    = source,
            summary   = f"OUTCOME {strategy_id}: {outcome}" + (f" pnl={pnl:.4f}" if pnl is not None else ""),
            body      = MappingProxyType(body),
            tags      = tags | frozenset(["outcome", strategy_id, outcome.lower()]),
        )
        with self._lock:
            self._outcomes.setdefault(strategy_id, []).append(outcome)
        self._store(rec)
        return rec

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_fitness_history(self, strategy_id: str) -> list[float]:
        with self._lock:
            return list(self._fitness.get(strategy_id, []))

    def get_outcome_history(self, strategy_id: str) -> list[str]:
        with self._lock:
            return list(self._outcomes.get(strategy_id, []))

    def recent(self, limit: int = 20) -> list[MemoryRecord]:
        with self._lock:
            recs = list(self._records)
        recs.sort(key=lambda r: r.ts_ns, reverse=True)
        return recs[:limit]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active":    True,
                "size":      len(self._records),
                "max_size":  self._max_size,
                "strategies": len(self._fitness),
                "fitness_tracked": sum(len(v) for v in self._fitness.values()),
                "outcomes_tracked": sum(len(v) for v in self._outcomes.values()),
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _store(self, rec: MemoryRecord) -> None:
        try:
            with self._lock:
                self._records.append(rec)
                self._by_id[rec.record_id] = rec
        except Exception as exc:
            _logger.debug("strategy_store._store error: %s", exc)


_singleton: StrategyMemoryStore | None = None
_lock = threading.Lock()


def get_strategy_memory_store() -> StrategyMemoryStore:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = StrategyMemoryStore()
    return _singleton


__all__ = ["StrategyMemoryStore", "get_strategy_memory_store"]
