"""
core/contracts/observability.py
DIX VISION v42.2 — Observability Protocol Contracts

Defines structural typing for metrics, tracing, and logging subsystems.
Concrete implementations (OpenTelemetry, Prometheus) satisfy these protocols.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class MetricType(StrEnum):
    """Types of metrics the observability layer can record."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class SpanStatus(StrEnum):
    """Trace span completion status."""

    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


@dataclass(frozen=True, slots=True)
class MetricPoint:
    """Single metric observation."""

    name: str
    value: float
    metric_type: MetricType
    labels: tuple[tuple[str, str], ...]
    ts_ns: int


@dataclass(frozen=True, slots=True)
class SpanContext:
    """Distributed trace span context."""

    trace_id: str
    span_id: str
    parent_span_id: str
    operation: str
    status: SpanStatus
    duration_ms: float


@runtime_checkable
class IObservability(Protocol):
    """Protocol: observability contract.

    Any metrics/tracing backend must satisfy this protocol to be
    plugged into the DIXVISION observability pipeline.
    """

    def observe(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        """Record a gauge/histogram observation.

        Args:
            name: Metric name (dotted notation, e.g. 'engine.latency_ms').
            value: Observed value.
            labels: Optional key-value labels for metric dimensions.
        """
        ...

    def increment(
        self, counter: str, *, labels: dict[str, str] | None = None, amount: float = 1.0
    ) -> None:
        """Increment a counter metric.

        Args:
            counter: Counter name.
            labels: Optional dimensional labels.
            amount: Increment amount (default 1.0).
        """
        ...

    def start_span(self, operation: str, *, parent: SpanContext | None = None) -> SpanContext:
        """Begin a trace span for an operation.

        Args:
            operation: Name of the operation being traced.
            parent: Optional parent span for distributed tracing.

        Returns:
            SpanContext for the new span (pass to end_span).
        """
        ...

    def end_span(self, span: SpanContext, *, status: SpanStatus = SpanStatus.OK) -> None:
        """End a trace span.

        Args:
            span: The span context to close.
            status: Completion status of the span.
        """
        ...

    def flush(self) -> None:
        """Flush all buffered metrics and traces to the backend."""
        ...


@runtime_checkable
class IHealthCheck(Protocol):
    """Protocol: health check endpoint for liveness/readiness probes."""

    def is_healthy(self) -> bool:
        """Return True if the component is healthy and operational."""
        ...

    def health_details(self) -> dict[str, bool]:
        """Return detailed health status per sub-component."""
        ...


__all__ = [
    "IHealthCheck",
    "IObservability",
    "MetricPoint",
    "MetricType",
    "SpanContext",
    "SpanStatus",
]
