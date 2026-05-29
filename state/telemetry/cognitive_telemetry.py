"""CognitiveTelemetry — live cognition traces (P3 Reality Layer).

Span-based telemetry for the cognitive pipeline.  Spans are collected by
subscribing to the cognitive event bus — no direct coupling to source modules.
Every INDIRA thought, DYON scan, research completion, and long-horizon
consolidation produces a span automatically once this module is activated.

Spans are kept in a bounded in-memory ring buffer and periodically flushed
to SQLite via CognitionPersistenceStore for durable queryability.

Dashboard surface:
    GET /api/telemetry/summary   — throughput + latency per component
    GET /api/telemetry/spans     — recent spans (newest first, paged)

Authority: pure state tier — no engine, no runtime, no execution imports.
INV-15: ts_ns from event payloads (always caller-supplied by publishers).
"""

from __future__ import annotations

import logging
import statistics
import threading
import time as _time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

_MAX_SPANS = 2_000          # in-memory ring buffer depth
_FLUSH_EVERY = 100          # flush to SQLite every N spans
_STORE_KIND = "telemetry_spans"


# ---------------------------------------------------------------------------
# TelemetrySpan
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TelemetrySpan:
    """One unit of telemetry: a labelled event with latency + metadata."""

    span_id: str
    component: str      # "indira" | "dyon" | "research" | "long_horizon"
    operation: str      # "thought" | "scan_complete" | "research_complete" | "consolidation"
    ts_ns: int
    elapsed_ms: float   # 0.0 when event-driven (no direct timing available)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "component": self.component,
            "operation": self.operation,
            "ts_ns": self.ts_ns,
            "elapsed_ms": self.elapsed_ms,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# CognitiveTelemetry
# ---------------------------------------------------------------------------


class CognitiveTelemetry:
    """Collects and stores cognitive span telemetry.

    Activated by calling ``activate()``.  After that, subscribes to the
    event bus and builds spans automatically from published events.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spans: deque[TelemetrySpan] = deque(maxlen=_MAX_SPANS)
        self._span_seq = 0
        self._flush_seq = 0
        self._activated = False
        self._counts: dict[str, int] = {}
        self._latencies: dict[str, list[float]] = {}

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Subscribe to the event bus.  Idempotent."""
        if self._activated:
            return
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            bus = get_event_bus()
            bus.subscribe(CognitiveChannel.INDIRA_THOUGHT, self._on_indira_thought)
            bus.subscribe(CognitiveChannel.DYON_SCAN_COMPLETE, self._on_dyon_scan)
            bus.subscribe(CognitiveChannel.DYON_PROPOSAL, self._on_dyon_proposal)
            bus.subscribe(CognitiveChannel.RESEARCH_COMPLETE, self._on_research_complete)
            bus.subscribe(CognitiveChannel.INDIRA_INSIGHT, self._on_indira_insight)
            bus.subscribe(CognitiveChannel.MARKET_TICK, self._on_market_tick)
            bus.subscribe(CognitiveChannel.RISK_BREACH, self._on_risk_breach)
            self._activated = True
            _logger.info("CognitiveTelemetry: activated — subscribed to 7 event bus channels")
        except Exception as exc:
            _logger.debug("CognitiveTelemetry.activate error: %s", exc)

    # ------------------------------------------------------------------
    # Direct recording (for callers that want explicit span instrumentation)
    # ------------------------------------------------------------------

    def record(
        self,
        component: str,
        operation: str,
        *,
        ts_ns: int,
        elapsed_ms: float = 0.0,
        **metadata: Any,
    ) -> TelemetrySpan:
        """Record a span directly.  Returns the created span."""
        with self._lock:
            self._span_seq += 1
            span_id = f"tel_{component[:6]}_{self._span_seq}_{ts_ns & 0xFFFF:04x}"
        span = TelemetrySpan(
            span_id=span_id,
            component=component,
            operation=operation,
            ts_ns=ts_ns,
            elapsed_ms=elapsed_ms,
            metadata=dict(metadata),
        )
        self._store(span)
        return span

    # ------------------------------------------------------------------
    # Query surface
    # ------------------------------------------------------------------

    def recent_spans(
        self,
        limit: int = 100,
        component: str | None = None,
    ) -> list[TelemetrySpan]:
        """Return the most recent spans, newest-first."""
        with self._lock:
            items = list(self._spans)
        items.reverse()
        if component:
            items = [s for s in items if s.component == component]
        return items[:limit]

    def summary(self) -> dict[str, Any]:
        """Per-component throughput + latency summary."""
        with self._lock:
            counts = dict(self._counts)
            lat = {k: list(v) for k, v in self._latencies.items()}
        components: dict[str, dict[str, Any]] = {}
        for key, n in counts.items():
            lats = lat.get(key, [])
            entry: dict[str, Any] = {"count": n}
            if lats:
                entry["latency_p50_ms"] = round(statistics.median(lats), 2)
                entry["latency_max_ms"] = round(max(lats), 2)
                entry["latency_mean_ms"] = round(statistics.mean(lats), 2)
            components[key] = entry
        return {
            "activated": self._activated,
            "total_spans": sum(counts.values()),
            "span_seq": self._span_seq,
            "flush_seq": self._flush_seq,
            "components": components,
        }

    # ------------------------------------------------------------------
    # Event bus handlers
    # ------------------------------------------------------------------

    def _on_indira_thought(self, payload: dict[str, Any]) -> None:
        ts_ns = int(payload.get("ts_ns", 0))
        self.record(
            "indira", "thought",
            ts_ns=ts_ns,
            step=payload.get("step", ""),
            confidence=payload.get("confidence", 0.0),
            thought_id=str(payload.get("thought_id", ""))[:20],
        )

    def _on_dyon_scan(self, payload: dict[str, Any]) -> None:
        ts_ns = int(payload.get("ts_ns", 0))
        self.record(
            "dyon", "scan_complete",
            ts_ns=ts_ns,
            elapsed_ms=float(payload.get("scan_duration_ms", 0.0)),
            files_scanned=payload.get("files_scanned", 0),
            violation_count=payload.get("violation_count", 0),
            critical_count=payload.get("critical_count", 0),
            clean=payload.get("clean", True),
        )

    def _on_dyon_proposal(self, payload: dict[str, Any]) -> None:
        ts_ns = int(payload.get("ts_ns", 0))
        self.record(
            "dyon", "proposal",
            ts_ns=ts_ns,
            severity=payload.get("severity", ""),
            invariant_id=payload.get("invariant_id", ""),
            source_module=str(payload.get("source_module", ""))[:40],
        )

    def _on_research_complete(self, payload: dict[str, Any]) -> None:
        ts_ns = int(payload.get("ts_ns", 0))
        self.record(
            "research", "research_complete",
            ts_ns=ts_ns,
            elapsed_ms=float(payload.get("elapsed_ms", 0.0)),
            topic=str(payload.get("topic", ""))[:60],
            status=payload.get("status", ""),
            trust_score=payload.get("trust_score", 0.0),
            pages_fetched=payload.get("pages_fetched", 0),
        )

    def _on_indira_insight(self, payload: dict[str, Any]) -> None:
        ts_ns = int(payload.get("ts_ns", 0))
        self.record(
            "long_horizon", "insight",
            ts_ns=ts_ns,
            subject=payload.get("subject", ""),
            confidence=payload.get("confidence", 0.0),
            evidence_count=payload.get("evidence_count", 0),
        )

    def _on_market_tick(self, payload: dict[str, Any]) -> None:
        ts_ns = int(payload.get("ts_ns", 0))
        self.record(
            "market", "tick",
            ts_ns=ts_ns,
            symbol=payload.get("symbol", ""),
            price=payload.get("price", 0.0),
            source=payload.get("source", ""),
        )

    def _on_risk_breach(self, payload: dict[str, Any]) -> None:
        ts_ns = int(payload.get("ts_ns", 0))
        self.record(
            "risk", "breach",
            ts_ns=ts_ns,
            halted=payload.get("halted", False),
            breach_reason=str(payload.get("breach_reason", ""))[:80],
            drawdown_ok=payload.get("drawdown_ok", True),
            exposure_ok=payload.get("exposure_ok", True),
            position_ok=payload.get("position_ok", True),
        )

    # ------------------------------------------------------------------
    # Internal storage
    # ------------------------------------------------------------------

    def _store(self, span: TelemetrySpan) -> None:
        key = f"{span.component}.{span.operation}"
        with self._lock:
            self._spans.append(span)
            self._counts[key] = self._counts.get(key, 0) + 1
            if span.elapsed_ms > 0:
                self._latencies.setdefault(key, []).append(span.elapsed_ms)
                # Cap latency history to avoid unbounded growth
                if len(self._latencies[key]) > 500:
                    self._latencies[key] = self._latencies[key][-500:]
            should_flush = self._span_seq % _FLUSH_EVERY == 0

        if should_flush:
            self._flush_to_sqlite(span.ts_ns)

    def _flush_to_sqlite(self, ts_ns: int) -> None:
        """Persist the last _FLUSH_EVERY spans to SQLite.  Best-effort."""
        try:
            from state.cognition_persistence import get_cognition_persistence_store
            with self._lock:
                self._flush_seq += 1
                recent = list(self._spans)[-_FLUSH_EVERY:]
            blobs = [s.to_dict() for s in recent]
            get_cognition_persistence_store().save_episode(
                store_kind=_STORE_KIND,
                episode_id=f"tel_flush_{self._flush_seq}",
                ts_ns=ts_ns,
                data={"spans": blobs, "flush_seq": self._flush_seq},
            )
        except Exception as exc:
            _logger.debug("CognitiveTelemetry._flush_to_sqlite error: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_telemetry: CognitiveTelemetry | None = None
_telemetry_lock = threading.Lock()


def get_cognitive_telemetry() -> CognitiveTelemetry:
    """Return the process-wide CognitiveTelemetry singleton (activated on first call)."""
    global _telemetry
    with _telemetry_lock:
        if _telemetry is None:
            _telemetry = CognitiveTelemetry()
            _telemetry.activate()
    return _telemetry


__all__ = [
    "CognitiveTelemetry",
    "TelemetrySpan",
    "get_cognitive_telemetry",
]
