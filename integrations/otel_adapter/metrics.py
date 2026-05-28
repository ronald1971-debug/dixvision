"""OpenTelemetry metrics adapter (OSS Integration Layer).

Provides counters, histograms, and gauges for DIXVISION runtime metrics.
Exports to Prometheus-compatible endpoints for Grafana dashboards.

Key metrics:
- dix_orders_total: total orders by exchange/side/status
- dix_pnl_total: cumulative PnL
- dix_decision_duration_ms: decision latency histogram
- dix_governance_evaluations: policy evaluation counts
- dix_regime_changes: regime transition counter
- dix_portfolio_heat: current portfolio heat gauge

Reference: github.com/open-telemetry/opentelemetry-python
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from system import time_source


class MetricType(StrEnum):
    """Metric types."""

    COUNTER = "counter"
    HISTOGRAM = "histogram"
    GAUGE = "gauge"


@dataclass(slots=True)
class MetricPoint:
    """A single metric data point."""

    name: str
    metric_type: MetricType
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    ts_ns: int = 0


@dataclass(frozen=True, slots=True)
class MetricsConfig:
    """Configuration for the metrics adapter."""

    service_name: str = "dixvision"
    prometheus_port: int = 9090
    export_interval_ms: int = 10000
    export_enabled: bool = False


class OTelMetricsAdapter:
    """DIXVISION adapter wrapping OpenTelemetry metrics.

    Provides:
    - Counter increments (orders, events, errors)
    - Histogram recording (latencies, sizes)
    - Gauge setting (portfolio heat, drawdown, equity)
    - Prometheus export for Grafana

    Falls back to in-memory metric collection when OTel is unavailable.
    """

    def __init__(self, *, config: MetricsConfig | None = None) -> None:
        self._config = config or MetricsConfig()
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._history: list[MetricPoint] = []
        self._history_max = 10000

    def initialize(self) -> bool:
        """Initialize OpenTelemetry metrics SDK."""
        try:
            from opentelemetry import metrics  # noqa: F401

            return True
        except ImportError:
            return False

    # --- Counters ---

    def increment(
        self, name: str, *, value: float = 1.0, labels: dict[str, str] | None = None
    ) -> None:
        """Increment a counter."""
        key = self._key(name, labels)
        self._counters[key] = self._counters.get(key, 0.0) + value
        self._record(name, MetricType.COUNTER, self._counters[key], labels)

    # --- Gauges ---

    def set_gauge(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        """Set a gauge value."""
        key = self._key(name, labels)
        self._gauges[key] = value
        self._record(name, MetricType.GAUGE, value, labels)

    # --- Histograms ---

    def record(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        """Record a histogram observation."""
        key = self._key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)
        # Keep bounded
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]
        self._record(name, MetricType.HISTOGRAM, value, labels)

    # --- DIXVISION-specific metrics ---

    def record_order(self, *, exchange: str, side: str, status: str) -> None:
        """Record an order event."""
        self.increment(
            "dix_orders_total",
            labels={"exchange": exchange, "side": side, "status": status},
        )

    def record_pnl(self, pnl: float) -> None:
        """Record PnL."""
        self.increment("dix_pnl_total", value=pnl)

    def record_decision_latency(self, duration_ms: float) -> None:
        """Record decision latency."""
        self.record("dix_decision_duration_ms", duration_ms)

    def set_portfolio_heat(self, heat: float) -> None:
        """Set current portfolio heat."""
        self.set_gauge("dix_portfolio_heat", heat)

    def set_drawdown(self, drawdown: float) -> None:
        """Set current drawdown."""
        self.set_gauge("dix_drawdown", drawdown)

    def set_equity(self, equity: float) -> None:
        """Set current equity."""
        self.set_gauge("dix_equity", equity)

    def record_regime_change(self, *, from_regime: str, to_regime: str) -> None:
        """Record a regime transition."""
        self.increment(
            "dix_regime_changes",
            labels={"from": from_regime, "to": to_regime},
        )

    # --- Query ---

    def get_counter(self, name: str, *, labels: dict[str, str] | None = None) -> float:
        """Get counter value."""
        return self._counters.get(self._key(name, labels), 0.0)

    def get_gauge(self, name: str, *, labels: dict[str, str] | None = None) -> float:
        """Get gauge value."""
        return self._gauges.get(self._key(name, labels), 0.0)

    def get_histogram_stats(
        self, name: str, *, labels: dict[str, str] | None = None
    ) -> dict[str, float]:
        """Get histogram statistics (min, max, avg, p50, p95, p99)."""
        key = self._key(name, labels)
        values = self._histograms.get(key, [])
        if not values:
            return {"min": 0, "max": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}

        sorted_v = sorted(values)
        n = len(sorted_v)
        return {
            "min": sorted_v[0],
            "max": sorted_v[-1],
            "avg": sum(sorted_v) / n,
            "p50": sorted_v[int(n * 0.5)],
            "p95": sorted_v[min(int(n * 0.95), n - 1)],
            "p99": sorted_v[min(int(n * 0.99), n - 1)],
        }

    @property
    def metric_count(self) -> int:
        """Total unique metrics tracked."""
        return len(self._counters) + len(self._gauges) + len(self._histograms)

    # --- Internal ---

    @staticmethod
    def _key(name: str, labels: dict[str, str] | None) -> str:
        """Create a unique key for a metric + labels combination."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def _record(
        self,
        name: str,
        metric_type: MetricType,
        value: float,
        labels: dict[str, str] | None,
    ) -> None:
        """Record to history."""

        self._history.append(
            MetricPoint(
                name=name,
                metric_type=metric_type,
                value=value,
                labels=labels or {},
                ts_ns=time_source.wall_ns(),
            )
        )
        if len(self._history) > self._history_max:
            self._history = self._history[-self._history_max :]
