"""state.memory.stores.trader — TraderMemoryStore.

Records trader archetype performance across regimes: win rates,
avg P&L, dominant behaviors, decay over time.

Feeds INDIRA's BehavioralClusterTracker with historical performance
context so it can weight archetype hypotheses accurately.
"""

from __future__ import annotations

import logging
import threading
from collections import deque, defaultdict
from types import MappingProxyType
from typing import Any

from state.memory.contracts import MemoryKind, MemoryRecord

_logger   = logging.getLogger(__name__)
_MAX_SIZE = 1_000


class TraderMemoryStore:
    """Tracks trader archetype performance history per regime."""

    def __init__(self, max_size: int = _MAX_SIZE) -> None:
        self._max_size  = max_size
        self._lock      = threading.Lock()
        self._records:  deque[MemoryRecord] = deque(maxlen=max_size)
        # archetype → regime → list of (win: bool, pnl: float)
        self._perf:     dict[str, dict[str, list[tuple[bool, float]]]] = defaultdict(lambda: defaultdict(list))

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record_performance(
        self,
        *,
        record_id:  str,
        archetype:  str,
        regime:     str,
        ts_ns:      int,
        win:        bool,
        pnl:        float,
        source:     str = "trader_modeling",
        tags:       frozenset[str] = frozenset(),
    ) -> MemoryRecord:
        rec = MemoryRecord(
            record_id = record_id,
            kind      = MemoryKind.TRADER,
            ts_ns     = ts_ns,
            source    = source,
            summary   = (
                f"TRADER {archetype} in {regime}: "
                f"{'WIN' if win else 'LOSS'} pnl={pnl:.4f}"
            ),
            body      = MappingProxyType({
                "archetype": archetype,
                "regime":    regime,
                "win":       "1" if win else "0",
                "pnl":       str(pnl),
            }),
            tags      = tags | frozenset([archetype, regime, "performance"]),
            confidence = 1.0 if win else 0.0,
        )
        with self._lock:
            self._records.append(rec)
            self._perf[archetype][regime].append((win, pnl))
        return rec

    def record_archetype_shift(
        self,
        *,
        record_id:  str,
        from_arch:  str,
        to_arch:    str,
        ts_ns:      int,
        reason:     str,
        source:     str = "behavioral_cluster",
        tags:       frozenset[str] = frozenset(),
    ) -> MemoryRecord:
        rec = MemoryRecord(
            record_id = record_id,
            kind      = MemoryKind.TRADER,
            ts_ns     = ts_ns,
            source    = source,
            summary   = f"ARCHETYPE SHIFT {from_arch} → {to_arch}: {reason}",
            body      = MappingProxyType({
                "from_archetype": from_arch,
                "to_archetype":   to_arch,
                "reason":         reason,
                "event":          "archetype_shift",
            }),
            tags      = tags | frozenset([from_arch, to_arch, "archetype_shift"]),
        )
        with self._lock:
            self._records.append(rec)
        return rec

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def win_rate(self, archetype: str, regime: str | None = None) -> float:
        """Return win rate for archetype, optionally filtered by regime."""
        with self._lock:
            if regime:
                entries = self._perf.get(archetype, {}).get(regime, [])
            else:
                entries = [e for r in self._perf.get(archetype, {}).values() for e in r]
        if not entries:
            return 0.0
        return round(sum(1 for w, _ in entries if w) / len(entries), 4)

    def avg_pnl(self, archetype: str, regime: str | None = None) -> float:
        with self._lock:
            if regime:
                entries = self._perf.get(archetype, {}).get(regime, [])
            else:
                entries = [e for r in self._perf.get(archetype, {}).values() for e in r]
        if not entries:
            return 0.0
        return round(sum(p for _, p in entries) / len(entries), 6)

    def leaderboard(self, regime: str | None = None, top_n: int = 10) -> list[dict]:
        with self._lock:
            archetypes = list(self._perf.keys())
        rows = []
        for arch in archetypes:
            wr   = self.win_rate(arch, regime)
            apnl = self.avg_pnl(arch, regime)
            rows.append({"archetype": arch, "win_rate": wr, "avg_pnl": apnl})
        rows.sort(key=lambda r: r["win_rate"], reverse=True)
        return rows[:top_n]

    def recent(self, limit: int = 20) -> list[MemoryRecord]:
        with self._lock:
            recs = list(self._records)
        recs.sort(key=lambda r: r.ts_ns, reverse=True)
        return recs[:limit]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total_entries = sum(
                len(entries)
                for regime_dict in self._perf.values()
                for entries in regime_dict.values()
            )
            return {
                "active":         True,
                "size":           len(self._records),
                "max_size":       self._max_size,
                "archetypes":     len(self._perf),
                "total_entries":  total_entries,
            }


_singleton: TraderMemoryStore | None = None
_lock = threading.Lock()


def get_trader_memory_store() -> TraderMemoryStore:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = TraderMemoryStore()
    return _singleton


__all__ = ["TraderMemoryStore", "get_trader_memory_store"]
