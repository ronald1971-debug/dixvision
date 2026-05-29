"""state.memory.index — MemoryIndexAuthority.

Inverted keyword index over MemoryRecord tags and summary tokens.
Enables fast cross-store keyword search without a vector query.

Design:
- In-process dict-based inverted index (token → set of record_ids)
- Tokens: tags + lowercased summary words (alpha-only, len >= 3)
- Thread-safe via a single RWLock simulation (one mutex)
- No external dependencies; no IO; no clock (INV-15)
"""

from __future__ import annotations

import logging
import re
import threading
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state.memory.contracts import MemoryRecord

_logger  = logging.getLogger(__name__)
_TOKENRE = re.compile(r"[a-z]{3,}")


def _tokenize(text: str) -> list[str]:
    return _TOKENRE.findall(text.lower())


class MemoryIndexAuthority:
    """Inverted index for cross-store keyword lookup."""

    def __init__(self) -> None:
        self._lock:    threading.Lock            = threading.Lock()
        self._index:   dict[str, set[str]]       = defaultdict(set)  # token → record_ids
        self._records: dict[str, "MemoryRecord"] = {}                # record_id → record
        self._total:   int                       = 0

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def index(self, record: "MemoryRecord") -> None:
        """Index one record. Idempotent (re-indexing same id is safe)."""
        try:
            tokens = set(_tokenize(record.summary))
            tokens.update(t.lower() for t in record.tags)
            tokens.update(_tokenize(record.source))
            with self._lock:
                self._records[record.record_id] = record
                for tok in tokens:
                    self._index[tok].add(record.record_id)
                self._total += 1
        except Exception as exc:
            _logger.debug("index.index error: %s", exc)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(self, keywords: list[str], limit: int = 20) -> list["MemoryRecord"]:
        """Return records matching ALL keywords (AND semantics)."""
        if not keywords:
            return []
        try:
            tokens = [kw.lower() for kw in keywords if len(kw) >= 3]
            if not tokens:
                return []
            with self._lock:
                candidate_sets = [self._index.get(t, set()) for t in tokens]
                if not candidate_sets:
                    return []
                ids = set.intersection(*candidate_sets)
                records = [self._records[rid] for rid in ids if rid in self._records]
            records.sort(key=lambda r: r.ts_ns, reverse=True)
            return records[:limit]
        except Exception as exc:
            _logger.debug("index.search error: %s", exc)
            return []

    def search_any(self, keywords: list[str], limit: int = 20) -> list["MemoryRecord"]:
        """Return records matching ANY keyword (OR semantics)."""
        if not keywords:
            return []
        try:
            tokens = [kw.lower() for kw in keywords if len(kw) >= 3]
            with self._lock:
                ids: set[str] = set()
                for t in tokens:
                    ids.update(self._index.get(t, set()))
                records = [self._records[rid] for rid in ids if rid in self._records]
            records.sort(key=lambda r: r.ts_ns, reverse=True)
            return records[:limit]
        except Exception as exc:
            _logger.debug("index.search_any error: %s", exc)
            return []

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active":       True,
                "indexed_records": len(self._records),
                "token_count":  len(self._index),
                "total_indexed": self._total,
            }


_singleton: MemoryIndexAuthority | None = None
_lock = threading.Lock()


def get_memory_index() -> MemoryIndexAuthority:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = MemoryIndexAuthority()
    return _singleton


__all__ = ["MemoryIndexAuthority", "get_memory_index"]
