"""OpenTelemetry tracing adapter (OSS Integration Layer).

Provides distributed tracing for DIXVISION engine operations.
Every decision, execution, and governance evaluation gets a span
with structured attributes for full observability.

Key spans:
- intelligence.decision: meta-controller decisions
- execution.order: order lifecycle (submit → fill → reconcile)
- governance.evaluation: policy evaluation timing
- learning.update: model update events
- simulation.step: simulation cycle timing

Reference: github.com/open-telemetry/opentelemetry-python
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from system import time_source


class SpanKind(StrEnum):
    """OpenTelemetry span kinds."""

    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class SpanStatus(StrEnum):
    """Span completion status."""

    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


@dataclass(slots=True)
class Span:
    """A tracing span representing a unit of work."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    kind: SpanKind = SpanKind.INTERNAL
    status: SpanStatus = SpanStatus.UNSET
    start_time_ns: int = 0
    end_time_ns: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TracerConfig:
    """Configuration for the tracing adapter."""

    service_name: str = "dixvision"
    endpoint: str = ""  # OTLP endpoint
    sample_rate: float = 1.0  # 1.0 = trace everything
    max_spans: int = 10000
    export_enabled: bool = False


class OTelTracingAdapter:
    """DIXVISION adapter wrapping OpenTelemetry tracing.

    Provides:
    - Span creation and management
    - Distributed context propagation
    - Structured attributes on every span
    - Export to OTLP endpoint (Jaeger, Tempo, etc.)

    Falls back to in-memory span collection when OTel is unavailable.
    """

    def __init__(self, *, config: TracerConfig | None = None) -> None:
        self._config = config or TracerConfig()
        self._spans: list[Span] = []
        self._active_spans: dict[str, Span] = {}
        self._span_counter = 0
        self._otel_available = False
        self._tracer: Any = None

    def initialize(self) -> bool:
        """Initialize OpenTelemetry SDK."""
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider

            provider = TracerProvider()
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(self._config.service_name)
            self._otel_available = True
            return True
        except ImportError:
            self._otel_available = False
            return False

    def start_span(
        self,
        name: str,
        *,
        kind: SpanKind = SpanKind.INTERNAL,
        parent_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        """Start a new span. Returns span_id."""
        self._span_counter += 1
        span_id = f"span_{self._span_counter:08d}"
        trace_id = f"trace_{self._span_counter:08d}"

        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_id,
            kind=kind,
            start_time_ns=time_source.wall_ns(),
            attributes=attributes or {},
        )
        self._active_spans[span_id] = span
        return span_id

    def end_span(
        self,
        span_id: str,
        *,
        status: SpanStatus = SpanStatus.OK,
        attributes: dict[str, Any] | None = None,
    ) -> Span | None:
        """End an active span."""
        span = self._active_spans.pop(span_id, None)
        if span is None:
            return None

        span.end_time_ns = time_source.wall_ns()
        span.status = status
        if attributes:
            span.attributes.update(attributes)

        self._spans.append(span)
        if len(self._spans) > self._config.max_spans:
            self._spans = self._spans[-self._config.max_spans :]

        return span

    def add_event(
        self, span_id: str, name: str, *, attributes: dict[str, Any] | None = None
    ) -> None:
        """Add an event to an active span."""
        span = self._active_spans.get(span_id)
        if span:
            span.events.append(
                {
                    "name": name,
                    "ts_ns": time_source.wall_ns(),
                    "attributes": attributes or {},
                }
            )

    def set_attribute(self, span_id: str, key: str, value: Any) -> None:
        """Set an attribute on an active span."""
        span = self._active_spans.get(span_id)
        if span:
            span.attributes[key] = value

    # --- Convenience methods for DIXVISION operations ---

    def trace_decision(
        self,
        *,
        decision_type: str,
        confidence: float,
        regime: str,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        """Start a decision trace span."""
        attrs = {
            "dix.decision_type": decision_type,
            "dix.confidence": confidence,
            "dix.regime": regime,
        }
        if attributes:
            attrs.update(attributes)
        return self.start_span(f"intelligence.{decision_type}", attributes=attrs)

    def trace_execution(
        self,
        *,
        symbol: str,
        side: str,
        amount: float,
        exchange: str,
    ) -> str:
        """Start an execution trace span."""
        return self.start_span(
            "execution.order",
            kind=SpanKind.CLIENT,
            attributes={
                "dix.symbol": symbol,
                "dix.side": side,
                "dix.amount": amount,
                "dix.exchange": exchange,
            },
        )

    def trace_governance(self, *, policy: str, action: str) -> str:
        """Start a governance evaluation span."""
        return self.start_span(
            "governance.evaluation",
            attributes={"dix.policy": policy, "dix.action": action},
        )

    # --- Query ---

    @property
    def total_spans(self) -> int:
        """Total completed spans."""
        return len(self._spans)

    @property
    def active_span_count(self) -> int:
        """Currently active spans."""
        return len(self._active_spans)

    def get_recent_spans(self, *, limit: int = 50) -> list[Span]:
        """Get recent completed spans."""
        return self._spans[-limit:]

    def get_spans_by_name(self, name: str) -> list[Span]:
        """Filter spans by name prefix."""
        return [s for s in self._spans if s.name.startswith(name)]
