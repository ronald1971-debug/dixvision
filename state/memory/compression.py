"""state.memory.compression — MemoryCompressor.

Episodic → Semantic compression: groups episodic records by source
within a time window and synthesizes a semantic summary record.

Rules:
- Groups EPISODIC records by source over a configurable window_ns
- If a group has >= min_group_size records, emits one SEMANTIC record
  whose summary concatenates the first N summaries (truncated)
- Dedup: only compresses once per (source, bucket)
- No clock reads (INV-15); compression is caller-driven via compress()
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import defaultdict
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state.memory.contracts import MemoryKind, MemoryRecord

_logger = logging.getLogger(__name__)

_WINDOW_NS      = 300_000_000_000    # 5-minute compression windows
_MIN_GROUP_SIZE = 3
_MAX_SUMMARY    = 200                # chars per merged summary


class MemoryCompressor:
    """Groups episodic memories and emits compressed semantic records."""

    def __init__(
        self,
        *,
        window_ns:      int = _WINDOW_NS,
        min_group_size: int = _MIN_GROUP_SIZE,
    ) -> None:
        self._window_ns      = window_ns
        self._min_group_size = min_group_size
        self._lock           = threading.Lock()
        self._compressed:    set[str] = set()   # (source, bucket) seen
        self._total_in:      int = 0
        self._total_out:     int = 0

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def compress(
        self,
        records: list["MemoryRecord"],
        *,
        ts_ns: int,
    ) -> list["MemoryRecord"]:
        """Compress a batch of EPISODIC records into SEMANTIC summaries.

        Returns the list of newly synthesized SEMANTIC records.
        Caller should write these to the semantic store.
        """
        from state.memory.contracts import MemoryKind
        try:
            episodics = [r for r in records if r.kind == MemoryKind.EPISODIC]
            self._total_in += len(episodics)

            groups: dict[tuple[str, int], list["MemoryRecord"]] = defaultdict(list)
            for r in episodics:
                bucket = r.ts_ns // self._window_ns
                groups[(r.source, bucket)].append(r)

            out: list["MemoryRecord"] = []
            for (source, bucket), group in groups.items():
                if len(group) < self._min_group_size:
                    continue
                key = f"{source}:{bucket}"
                with self._lock:
                    if key in self._compressed:
                        continue
                    self._compressed.add(key)
                semantic = self._synthesize(group, ts_ns=ts_ns)
                out.append(semantic)
                self._total_out += 1
            return out
        except Exception as exc:
            _logger.debug("compressor.compress error: %s", exc)
            return []

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active":           True,
                "total_episodic_in": self._total_in,
                "total_semantic_out": self._total_out,
                "buckets_compressed": len(self._compressed),
                "compression_ratio": (
                    round(self._total_out / self._total_in, 4)
                    if self._total_in else 0.0
                ),
            }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _synthesize(
        self,
        group: list["MemoryRecord"],
        *,
        ts_ns: int,
    ) -> "MemoryRecord":
        from state.memory.contracts import MemoryKind, MemoryRecord
        group.sort(key=lambda r: r.ts_ns)
        summaries = "; ".join(r.summary for r in group)
        merged    = summaries[:_MAX_SUMMARY]
        source    = group[0].source
        avg_conf  = sum(r.confidence for r in group if r.confidence >= 0)
        n_conf    = sum(1 for r in group if r.confidence >= 0)
        confidence = round(avg_conf / n_conf, 4) if n_conf else -1.0
        all_tags  = frozenset(t for r in group for t in r.tags)
        rid_raw   = f"compress|{source}|{ts_ns}|{merged}"
        rid       = "mem-sem-" + hashlib.sha256(rid_raw.encode()).hexdigest()[:20]
        return MemoryRecord(
            record_id  = rid,
            kind       = MemoryKind.SEMANTIC,
            ts_ns      = ts_ns,
            source     = f"compressor:{source}",
            summary    = f"[compressed {len(group)}] {merged}",
            body       = MappingProxyType({"origin_count": str(len(group)), "source": source}),
            tags       = all_tags | frozenset(["compressed"]),
            confidence = confidence,
        )


_singleton: MemoryCompressor | None = None
_lock = threading.Lock()


def get_memory_compressor() -> MemoryCompressor:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = MemoryCompressor()
    return _singleton


__all__ = ["MemoryCompressor", "get_memory_compressor"]
