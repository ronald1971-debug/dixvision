"""core.contracts.logger — Structured Logging Protocol (System Spec §Observability).

Production logging contract. All log entries are structured JSON with correlation
IDs for distributed tracing. Logs feed into the authority ledger for replay and
audit. No unstructured print() or bare logging calls in hot paths.

Severity levels map to governance response:
- CRITICAL → HazardEvent emission, drift oracle evaluation
- ERROR → logged + metrics incremented
- WARNING → advisory only (no WARNING for operator choices — use ledger)
- INFO → telemetry stream
- DEBUG → development only, stripped in production builds
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Protocol, runtime_checkable


class LogLevel(IntEnum):
    """Structured log severity levels."""

    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


@dataclass(frozen=True, slots=True)
class LogEntry:
    """Structured log entry with full provenance."""

    level: LogLevel
    message: str
    source: str
    trace_id: str
    ts_ns: int
    fields: dict[str, Any]
    error: str = ""
    stack_trace: str = ""


@dataclass(frozen=True, slots=True)
class LogConfig:
    """Logger configuration."""

    min_level: LogLevel = LogLevel.INFO
    structured: bool = True
    output_json: bool = True
    include_trace_id: bool = True
    include_source: bool = True
    max_field_depth: int = 3
    buffer_size: int = 1000


@runtime_checkable
class ILogger(Protocol):
    """Protocol: structured logger contract.

    Concrete implementations output JSON to stdout/file and feed the
    telemetry pipeline. CRITICAL logs trigger HazardEvent construction
    by Dyon (INV-71).
    """

    def debug(self, msg: str, *, source: str = "", trace_id: str = "", **fields: Any) -> None:
        """Log at DEBUG level (development only)."""
        ...

    def info(self, msg: str, *, source: str = "", trace_id: str = "", **fields: Any) -> None:
        """Log at INFO level (telemetry stream)."""
        ...

    def warning(self, msg: str, *, source: str = "", trace_id: str = "", **fields: Any) -> None:
        """Log at WARNING level (advisory, not for operator choices)."""
        ...

    def error(
        self, msg: str, *, source: str = "", trace_id: str = "", error: str = "", **fields: Any
    ) -> None:
        """Log at ERROR level (metrics incremented, no hazard)."""
        ...

    def critical(
        self, msg: str, *, source: str = "", trace_id: str = "", error: str = "", **fields: Any
    ) -> None:
        """Log at CRITICAL level (HazardEvent emission by Dyon)."""
        ...

    def with_context(self, **fields: Any) -> ILogger:
        """Return a child logger with additional default fields."""
        ...

    @property
    def level(self) -> LogLevel:
        """Current minimum log level."""
        ...


@runtime_checkable
class IAuditLogger(Protocol):
    """Protocol: audit logger that writes to the authority ledger.

    Every Class B/C mutation, every mode transition, every operator action
    passes through this for immutable recording.
    """

    def log(self, event_kind: str, source: str, payload: dict[str, Any]) -> None:
        """Append an audit entry to the authority ledger.

        Args:
            event_kind: SystemEventKind enum value.
            source: Subsystem that produced the event.
            payload: Structured payload (must be JSON-serializable).
        """
        ...

    def log_operator_action(self, action: str, operator_id: str, payload: dict[str, Any]) -> None:
        """Log an operator-initiated action with provenance."""
        ...


__all__ = [
    "IAuditLogger",
    "ILogger",
    "LogConfig",
    "LogEntry",
    "LogLevel",
]
