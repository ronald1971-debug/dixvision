"""observability.tracing — Manifest-canonical alias for observability.traces."""

from observability.traces import Span, TraceManager, get_trace_manager

__all__ = ["Span", "TraceManager", "get_trace_manager"]
