"""state.memory.unified — UnifiedMemoryLayer.

Top-level coordinator for the Unified Cognitive Memory Layer (Stage 4).

Responsibilities:
1. Receive MemoryRecord writes from any subsystem
2. Route to domain-specific store (strategy/trader/governance/runtime)
3. Append every record to CognitionTimeline (persistent log)
4. Index every record in MemoryIndexAuthority (keyword search)
5. Assign stable IDs via MemoryIdentitySystem (dedup)
6. Run periodic compression (episodic → semantic) via MemoryCompressor
7. Expose cross-store query interface

Architecture invariants:
- No engine imports (pure state tier)
- No clock reads (INV-15); ts_ns always caller-supplied
- All writes are best-effort (never raise to caller)
- Thread-safe via per-store locks
"""

from __future__ import annotations

import logging
import threading
from types import MappingProxyType
from typing import Any

from state.memory.contracts import MemoryKind, MemoryRecord, MemoryQuery, MemorySearchResult

_logger = logging.getLogger(__name__)


class UnifiedMemoryLayer:
    """Routes writes and cross-store queries across the full memory stack."""

    def __init__(self) -> None:
        self._lock       = threading.Lock()
        self._write_seq: int = 0
        self._active:    bool = False

        # lazily loaded subsystems
        self._identity:    Any = None
        self._timeline:    Any = None
        self._index:       Any = None
        self._compressor:  Any = None
        self._strategy:    Any = None
        self._trader:      Any = None
        self._governance:  Any = None
        self._runtime_ev:  Any = None

        # compression: buffer episodic records between compress() calls
        self._episodic_buf: list[MemoryRecord] = []
        self._compress_seq: int = 0

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Lazy-load all subsystems. Called once at boot."""
        try:
            from state.memory.identity    import get_memory_identity_system
            from state.memory.timeline    import get_cognition_timeline
            from state.memory.index       import get_memory_index
            from state.memory.compression import get_memory_compressor
            from state.memory.stores.strategy      import get_strategy_memory_store
            from state.memory.stores.trader        import get_trader_memory_store
            from state.memory.stores.governance    import get_governance_memory_store
            from state.memory.stores.runtime_events import get_runtime_event_memory_store

            self._identity   = get_memory_identity_system()
            self._timeline   = get_cognition_timeline()
            self._index      = get_memory_index()
            self._compressor = get_memory_compressor()
            self._strategy   = get_strategy_memory_store()
            self._trader     = get_trader_memory_store()
            self._governance = get_governance_memory_store()
            self._runtime_ev = get_runtime_event_memory_store()
            self._active     = True
            _logger.info("UnifiedMemoryLayer: activated — 8 subsystems online")
        except Exception as exc:
            _logger.warning("UnifiedMemoryLayer.activate error: %s", exc)

    # ------------------------------------------------------------------
    # Universal write
    # ------------------------------------------------------------------

    def write(
        self,
        *,
        kind:       MemoryKind,
        ts_ns:      int,
        source:     str,
        summary:    str,
        body:       dict[str, str] | None = None,
        tags:       frozenset[str] | None = None,
        confidence: float = -1.0,
        parent_id:  str | None = None,
    ) -> MemoryRecord | None:
        """Create, identify, persist, and index one MemoryRecord.

        Returns the written MemoryRecord, or None on failure.
        """
        if not self._active:
            return None
        try:
            if self._identity is None:
                return None
            record_id, is_new = self._identity.assign(
                kind=kind, source=source, summary=summary, ts_ns=ts_ns
            )
            if not is_new:
                return None   # duplicate within 60s window

            rec = MemoryRecord(
                record_id  = record_id,
                kind       = kind,
                ts_ns      = ts_ns,
                source     = source,
                summary    = summary,
                body       = MappingProxyType(body or {}),
                tags       = tags or frozenset(),
                confidence = confidence,
                parent_id  = parent_id,
            )

            # Timeline + index (always)
            if self._timeline:
                self._timeline.append(rec)
            if self._index:
                self._index.index(rec)

            # Domain routing
            self._route_to_domain(rec)

            # Episodic buffer for compression
            if kind == MemoryKind.EPISODIC:
                with self._lock:
                    self._episodic_buf.append(rec)

            with self._lock:
                self._write_seq += 1

            return rec
        except Exception as exc:
            _logger.debug("unified.write error: %s", exc)
            return None

    def write_record(self, rec: MemoryRecord) -> bool:
        """Write a pre-built MemoryRecord. Skips identity assignment."""
        if not self._active:
            return False
        try:
            if self._timeline:
                self._timeline.append(rec)
            if self._index:
                self._index.index(rec)
            self._route_to_domain(rec)
            if rec.kind == MemoryKind.EPISODIC:
                with self._lock:
                    self._episodic_buf.append(rec)
            with self._lock:
                self._write_seq += 1
            return True
        except Exception as exc:
            _logger.debug("unified.write_record error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Compression trigger (called by MemoryCoordinator periodically)
    # ------------------------------------------------------------------

    def compress(self, *, ts_ns: int) -> int:
        """Run episodic → semantic compression on the current buffer.

        Returns number of new semantic records emitted.
        """
        if not self._active or self._compressor is None:
            return 0
        try:
            with self._lock:
                buf = list(self._episodic_buf)
                self._episodic_buf.clear()
                self._compress_seq += 1

            new_semantics = self._compressor.compress(buf, ts_ns=ts_ns)
            for sem in new_semantics:
                self.write_record(sem)
            return len(new_semantics)
        except Exception as exc:
            _logger.debug("unified.compress error: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Cross-store query
    # ------------------------------------------------------------------

    def query(self, q: MemoryQuery) -> MemorySearchResult:
        """Keyword + time-range search across all stores via the index."""
        try:
            if not self._active or self._index is None:
                return MemorySearchResult(
                    query_id=q.query_id, ts_ns=q.ts_ns, records=(), total=0
                )
            if q.keywords:
                records = self._index.search(list(q.keywords), limit=q.limit * 2)
            else:
                records = list(self._index._records.values()) if self._index else []

            if q.kinds:
                records = [r for r in records if r.kind in q.kinds]
            if q.since_ns:
                records = [r for r in records if r.ts_ns >= q.since_ns]
            if q.until_ns:
                records = [r for r in records if r.ts_ns <= q.until_ns]
            if q.source:
                records = [r for r in records if r.source == q.source]

            records.sort(key=lambda r: r.ts_ns, reverse=True)
            page = records[: q.limit]
            return MemorySearchResult(
                query_id=q.query_id,
                ts_ns=q.ts_ns,
                records=tuple(page),
                total=len(records),
            )
        except Exception as exc:
            _logger.debug("unified.query error: %s", exc)
            return MemorySearchResult(
                query_id=q.query_id, ts_ns=q.ts_ns, records=(), total=0
            )

    def timeline_query(self, **kwargs: Any) -> list[dict]:
        """Direct pass-through to CognitionTimeline.query()."""
        if self._timeline:
            return self._timeline.query(**kwargs)
        return []

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            buf_size = len(self._episodic_buf)
            write_seq = self._write_seq
            compress_seq = self._compress_seq
        return {
            "active":        self._active,
            "write_seq":     write_seq,
            "compress_seq":  compress_seq,
            "episodic_buf":  buf_size,
            "identity":      self._identity.snapshot()   if self._identity   else None,
            "timeline":      self._timeline.snapshot()   if self._timeline   else None,
            "index":         self._index.snapshot()      if self._index      else None,
            "compressor":    self._compressor.snapshot() if self._compressor else None,
            "strategy":      self._strategy.snapshot()   if self._strategy   else None,
            "trader":        self._trader.snapshot()     if self._trader     else None,
            "governance":    self._governance.snapshot() if self._governance else None,
            "runtime_events": self._runtime_ev.snapshot() if self._runtime_ev else None,
        }

    # ------------------------------------------------------------------
    # Domain routing
    # ------------------------------------------------------------------

    def _route_to_domain(self, rec: MemoryRecord) -> None:
        try:
            if rec.kind == MemoryKind.STRATEGY and self._strategy:
                # Generic write to timeline is sufficient; strategy store
                # is populated via its own typed methods from evolution_engine.
                pass
            elif rec.kind == MemoryKind.TRADER and self._trader:
                pass
            elif rec.kind == MemoryKind.GOVERNANCE and self._governance:
                pass
            elif rec.kind == MemoryKind.RUNTIME and self._runtime_ev:
                pass
        except Exception as exc:
            _logger.debug("unified._route_to_domain error: %s", exc)


_singleton: UnifiedMemoryLayer | None = None
_lock = threading.Lock()


def get_unified_memory_layer() -> UnifiedMemoryLayer:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = UnifiedMemoryLayer()
    return _singleton


__all__ = ["UnifiedMemoryLayer", "get_unified_memory_layer"]
