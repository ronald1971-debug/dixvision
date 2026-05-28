"""observability.tracing.trace_manager — Manifest-canonical re-export.

The manifest directory tree places trace_manager.py under observability/tracing/.
The canonical implementation lives in observability/traces/trace_manager.py.
This module re-exports so both import paths work identically.
"""

from observability.traces.trace_manager import Span, TraceManager, get_trace_manager

__all__ = ["Span", "TraceManager", "get_trace_manager"]
