"""Cockpit widget — decision trace viewer.

Displays the reasoning chain behind the most recent AI decisions.
Read-only. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["DecisionTraceEntry", "DecisionTraceWidget"]


@dataclass(frozen=True, slots=True)
class TraceStep:
    step: int
    component: str
    input_summary: str
    output_summary: str
    confidence: float
    latency_ns: int


@dataclass(frozen=True, slots=True)
class DecisionTraceEntry:
    ts_ns: int
    strategy_id: str
    decision: str         # final decision label
    steps: tuple[TraceStep, ...]
    total_latency_ns: int
    override_applied: bool


class DecisionTraceWidget:
    """Read interface for decision trace data."""

    def __init__(self, trace_store: Any) -> None:
        self._store = trace_store

    def latest(self, strategy_id: str | None = None, limit: int = 20) -> tuple[DecisionTraceEntry, ...]:
        entries = self._store.recent(limit=limit)
        if strategy_id is not None:
            entries = [e for e in entries if e.strategy_id == strategy_id]
        return tuple(entries[:limit])

    def since(self, ts_ns: int) -> tuple[DecisionTraceEntry, ...]:
        return tuple(self._store.since(ts_ns))

    def format_entry(self, entry: DecisionTraceEntry) -> str:
        lines = [f"Decision: {entry.decision}  strategy={entry.strategy_id}  "
                 f"latency={entry.total_latency_ns/1e6:.2f}ms"]
        for step in entry.steps:
            lines.append(
                f"  [{step.step}] {step.component}: {step.input_summary} "
                f"→ {step.output_summary}  conf={step.confidence:.2f}"
            )
        if entry.override_applied:
            lines.append("  [OVERRIDE APPLIED]")
        return "\n".join(lines)
