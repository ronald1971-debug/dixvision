"""runtime.telemetry_aggregator — Unified Telemetry Aggregator.

Collects metrics from ALL subsystems into one queryable surface:

  Event throughput  — events/min per CognitiveChannel
  Memory metrics    — episodic/semantic/procedural sizes + write rate
  Cognitive rates   — INDIRA thought rate, DYON scan rate
  Risk metrics      — drawdown, halted state, positions
  System health     — spine phase errors, scheduler urgency backlog

Activation:
  - Subscribes to all 8 cognitive event bus channels (counts events)
  - poll(ts_ns) is called each kernel tick to sample gauges from singletons

The aggregator never raises.  All reads are best-effort.

Authority: runtime tier — imports state.*, runtime.* only.
INV-15: ts_ns caller-supplied.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

_logger = logging.getLogger(__name__)

# Rolling window for throughput calculation (seconds)
_WINDOW_S = 60.0


class TelemetryAggregator:
    """Unified metrics from all cognitive and execution subsystems."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        # event timestamps per channel, used for throughput calculation
        self._channel_ts: dict[str, deque] = {}
        # gauge snapshots (latest value per metric key)
        self._gauges: dict[str, float] = {}
        # poll sequence
        self._poll_seq = 0
        self._last_poll_ns = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Subscribe to all cognitive channels.  Idempotent."""
        with self._lock:
            if self._active:
                return
            self._active = True

        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            bus = get_event_bus()
            for ch in CognitiveChannel:
                name = ch.name
                self._channel_ts[name] = deque()
                _ch = ch
                _name = name
                bus.subscribe(_ch, lambda p, n=_name: self._on_event(n))
            _logger.info("TelemetryAggregator: activated (%d channels)", len(self._channel_ts))
        except Exception as exc:
            _logger.debug("TelemetryAggregator.activate error: %s", exc)

    def poll(self, ts_ns: int) -> None:
        """Sample gauges from all singletons.  Called each kernel tick."""
        try:
            self._poll_seq += 1
            self._last_poll_ns = ts_ns
            self._sample_risk()
            self._sample_indira()
            self._sample_dyon()
            self._sample_memory()
            self._sample_spine()
        except Exception as exc:
            _logger.debug("TelemetryAggregator.poll error: %s", exc)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return throughput + gauge summary."""
        now = time.monotonic()
        throughput: dict[str, float] = {}
        with self._lock:
            for ch_name, ts_deque in self._channel_ts.items():
                # Prune events older than window
                cutoff = now - _WINDOW_S
                while ts_deque and ts_deque[0] < cutoff:
                    ts_deque.popleft()
                # events/min
                throughput[ch_name] = len(ts_deque) * (60.0 / _WINDOW_S)
            gauges = dict(self._gauges)

        return {
            "poll_seq": self._poll_seq,
            "window_s": _WINDOW_S,
            "throughput_per_min": throughput,
            "gauges": gauges,
            "total_events": sum(len(d) for d in self._channel_ts.values()),
        }

    def gauge(self, key: str) -> float:
        """Get a specific gauge value."""
        with self._lock:
            return self._gauges.get(key, 0.0)

    def snapshot(self) -> dict[str, Any]:
        return self.summary()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_event(self, channel_name: str) -> None:
        now = time.monotonic()
        with self._lock:
            if channel_name in self._channel_ts:
                self._channel_ts[channel_name].append(now)

    def _set_gauge(self, key: str, value: float) -> None:
        with self._lock:
            self._gauges[key] = value

    def _sample_risk(self) -> None:
        try:
            from governance_engine.risk_engine.risk_tracker import get_risk_tracker
            snap = get_risk_tracker().snapshot()
            self._set_gauge("risk.halted", float(snap.get("halted", False)))
            self._set_gauge("risk.drawdown_pct", float(snap.get("drawdown_pct", 0.0)))
            self._set_gauge("risk.positions", float(len(snap.get("open_positions", {}))))
        except Exception:
            pass

    def _sample_indira(self) -> None:
        try:
            from intelligence_engine.cognitive.indira_runtime import get_indira_runtime
            snap = get_indira_runtime().snapshot()
            self._set_gauge("indira.tick_count", float(snap.get("tick_count", 0)))
            self._set_gauge("indira.thought_count", float(snap.get("thought_count", 0)))
            self._set_gauge("indira.confidence", float(snap.get("confidence_baseline", 0.0)))
        except Exception:
            pass

    def _sample_dyon(self) -> None:
        try:
            from evolution_engine.dyon.dyon_runtime import get_dyon_runtime
            snap = get_dyon_runtime().snapshot()
            self._set_gauge("dyon.tick_count", float(snap.get("tick_count", 0)))
            self._set_gauge("dyon.violation_count", float(snap.get("violation_count", 0)))
            self._set_gauge("dyon.proposal_count", float(snap.get("proposal_count", 0)))
        except Exception:
            pass

    def _sample_memory(self) -> None:
        try:
            from state.memory_tensor.memory_orchestrator import get_memory_orchestrator
            snap = get_memory_orchestrator().snapshot()
            self._set_gauge("memory.episodic", float(snap.get("episodic_size", 0)))
            self._set_gauge("memory.semantic", float(snap.get("semantic_size", 0)))
            self._set_gauge("memory.procedural", float(snap.get("procedural_size", 0)))
            self._set_gauge("memory.consolidate_seq", float(snap.get("consolidate_seq", 0)))
        except Exception:
            pass

    def _sample_spine(self) -> None:
        try:
            from runtime.cognitive_spine import get_cognitive_spine
            snap = get_cognitive_spine().snapshot()
            errors = snap.get("phase_errors", {})
            for phase, count in errors.items():
                self._set_gauge(f"spine.errors.{phase}", float(count))
            self._set_gauge("spine.tick_seq", float(snap.get("tick_seq", 0)))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_aggregator: TelemetryAggregator | None = None
_aggregator_lock = threading.Lock()


def get_telemetry_aggregator() -> TelemetryAggregator:
    global _aggregator
    with _aggregator_lock:
        if _aggregator is None:
            _aggregator = TelemetryAggregator()
    return _aggregator


__all__ = [
    "TelemetryAggregator",
    "get_telemetry_aggregator",
]
