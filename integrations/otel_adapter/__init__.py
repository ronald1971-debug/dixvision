"""OpenTelemetry Observability Adapter.

Replaces custom telemetry/metrics stacks with OpenTelemetry —
the industry standard for distributed tracing, metrics, and logging.

Maps DIXVISION observability:
- Engine execution spans → OTel traces
- Performance metrics → OTel metrics (counters, histograms, gauges)
- Decision audit → OTel structured logs
- System health → OTel health checks

Reference: github.com/open-telemetry/opentelemetry-python
"""
