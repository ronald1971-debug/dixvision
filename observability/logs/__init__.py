"""observability.logs — Structured log sink interface."""

from .log_sink import LogRecord, LogSink, get_log_sink, install_global_sink

__all__ = ["LogRecord", "LogSink", "get_log_sink", "install_global_sink"]
