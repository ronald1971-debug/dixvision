"""ObservabilityPipeline — unified observability entry point (CONSOLIDATION PHASE).

Single façade routing every observability signal to the correct sink:

    cognitive / ledger events  → state.ledger.event_store.append_event()
    metrics                    → observability.metrics.MetricsRegistry
    traces                     → observability.tracing.TraceManager
    logs                       → observability.logs.LogSink
    alerts                     → observability.alerts.AlertEngine

Nothing in the codebase should import individual sinks directly for
cross-cutting concerns. Engine-internal emitters (e.g. observability_emitter)
write to the ledger tier because they ARE the ledger tier; this pipeline
is for callers that need to span more than one sink in one call.

Authority: observability tier — may import state.ledger, not execution.
"""

from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)


class ObservabilityPipeline:
    """Routes observability events to all registered sinks.

    All methods are best-effort — a failing sink never raises to the caller.
    """

    # ------------------------------------------------------------------
    # Cognitive / ledger events
    # ------------------------------------------------------------------

    def record_cognitive(
        self,
        channel: str,
        sub_type: str,
        source: str,
        payload: dict[str, Any],
    ) -> None:
        """Append a cognitive event to the ledger and publish to the stream router."""
        try:
            from state.ledger.event_store import append_event
            append_event(channel, sub_type, source, payload)
        except Exception as exc:
            _logger.debug("ObservabilityPipeline.record_cognitive failed: %s", exc)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def increment(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        try:
            from observability.metrics import get_metrics_registry
            reg = get_metrics_registry()
            if hasattr(reg, "increment"):
                reg.increment(name, value, labels or {})
        except Exception:
            pass

    def gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        try:
            from observability.metrics import get_metrics_registry
            reg = get_metrics_registry()
            if hasattr(reg, "gauge"):
                reg.gauge(name, value, labels or {})
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Traces
    # ------------------------------------------------------------------

    def trace(self, name: str, ts_ns: int, duration_ns: int = 0, tags: dict[str, str] | None = None) -> None:
        try:
            from observability.tracing import TraceManager
            mgr = TraceManager()
            if hasattr(mgr, "record"):
                mgr.record(name=name, ts_ns=ts_ns, duration_ns=duration_ns, tags=tags or {})
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    def log(self, level: str, message: str, context: dict[str, Any] | None = None) -> None:
        try:
            from observability.logs import get_log_sink
            sink = get_log_sink()
            if hasattr(sink, "emit"):
                sink.emit(level=level, message=message, context=context or {})
            else:
                getattr(_logger, level.lower(), _logger.info)(message)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def alert(self, rule_id: str, payload: dict[str, Any]) -> None:
        try:
            from observability.alerts import get_alert_engine
            engine = get_alert_engine()
            if hasattr(engine, "evaluate"):
                engine.evaluate(rule_id=rule_id, payload=payload)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Status snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        try:
            from observability.metrics import get_metrics_registry
            reg = get_metrics_registry()
            metrics = reg.snapshot() if hasattr(reg, "snapshot") else {}
        except Exception:
            metrics = {}
        return {"pipeline": "ObservabilityPipeline", "metrics": metrics}


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_pipeline: ObservabilityPipeline | None = None


def get_pipeline() -> ObservabilityPipeline:
    """Return the module-level singleton ObservabilityPipeline."""
    global _pipeline
    if _pipeline is None:
        _pipeline = ObservabilityPipeline()
    return _pipeline


__all__ = [
    "ObservabilityPipeline",
    "get_pipeline",
]
