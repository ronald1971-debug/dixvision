"""runtime.unified_fabric.tracing — EventTracer.

Span-based trace_id propagation across the Unified Event Fabric.

Every UnifiedEvent carries a trace_id. When an event spawns children
(causal chain), children inherit the parent's trace_id. The EventTracer
records TraceSpans and organizes them into trace trees for operator view.

Design:
- 2000-span ring buffer (in-process, no DB dependency)
- Thread-safe
- No clock reads (INV-15) — ts_ns from events
- Get full trace tree by trace_id
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import defaultdict, deque
from typing import TYPE_CHECKING

from runtime.unified_fabric.contracts import FabricDomain, TraceSpan

if TYPE_CHECKING:
    from runtime.unified_fabric.contracts import UnifiedEvent

_logger   = logging.getLogger(__name__)
_RING_MAX = 2_000


class EventTracer:
    """Records and organizes TraceSpans for operator observability."""

    def __init__(self, ring_max: int = _RING_MAX) -> None:
        self._ring_max  = ring_max
        self._lock      = threading.Lock()
        self._ring:     deque[TraceSpan] = deque(maxlen=ring_max)
        self._by_trace: dict[str, list[TraceSpan]] = defaultdict(list)
        self._by_event: dict[str, TraceSpan]        = {}
        self._total:    int = 0

    # ------------------------------------------------------------------
    # Record
    # ------------------------------------------------------------------

    def record(self, event: "UnifiedEvent") -> TraceSpan:
        """Create and store a TraceSpan for this event. Returns the span."""
        try:
            span_id = self._make_span_id(event.event_id, event.trace_id)
            parent_span_id = ""
            if event.parent_id and event.parent_id in self._by_event:
                parent_span_id = self._by_event[event.parent_id].span_id

            span = TraceSpan(
                span_id        = span_id,
                trace_id       = event.trace_id,
                parent_span_id = parent_span_id,
                event_id       = event.event_id,
                domain         = event.domain,
                event_type     = event.event_type,
                ts_ns          = event.ts_ns,
                source         = event.source,
            )
            with self._lock:
                self._ring.append(span)
                self._by_trace[event.trace_id].append(span)
                self._by_event[event.event_id] = span
                self._total += 1
            return span
        except Exception as exc:
            _logger.debug("EventTracer.record error: %s", exc)
            return TraceSpan(
                span_id="", trace_id="", parent_span_id="",
                event_id="", domain=FabricDomain.UNKNOWN,
                event_type="", ts_ns=1, source="",
            )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_trace(self, trace_id: str) -> list[TraceSpan]:
        """Return all spans for a trace, ordered by ts_ns."""
        with self._lock:
            spans = list(self._by_trace.get(trace_id, []))
        spans.sort(key=lambda s: s.ts_ns)
        return spans

    def recent(self, limit: int = 50) -> list[TraceSpan]:
        """Return the most recent spans (newest-first)."""
        with self._lock:
            spans = list(self._ring)
        spans.sort(key=lambda s: s.ts_ns, reverse=True)
        return spans[:limit]

    def active_traces(self, limit: int = 20) -> list[dict]:
        """Return traces with >= 2 spans (multi-hop chains), newest-first."""
        with self._lock:
            traces = {
                tid: spans
                for tid, spans in self._by_trace.items()
                if len(spans) >= 2
            }
        rows = [
            {
                "trace_id":   tid,
                "span_count": len(spans),
                "domains":    sorted({s.domain.value for s in spans}),
                "first_ts":   min(s.ts_ns for s in spans),
                "last_ts":    max(s.ts_ns for s in spans),
            }
            for tid, spans in traces.items()
        ]
        rows.sort(key=lambda r: r["last_ts"], reverse=True)
        return rows[:limit]

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active":       True,
                "total_spans":  self._total,
                "ring_size":    len(self._ring),
                "ring_max":     self._ring_max,
                "total_traces": len(self._by_trace),
                "active_traces": sum(
                    1 for spans in self._by_trace.values() if len(spans) >= 2
                ),
            }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _make_span_id(event_id: str, trace_id: str) -> str:
        raw = f"{trace_id}|{event_id}"
        return "sp-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


_singleton: EventTracer | None = None
_lock = threading.Lock()


def get_event_tracer() -> EventTracer:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = EventTracer()
    return _singleton


__all__ = ["EventTracer", "get_event_tracer"]
