"""runtime.cognition_scheduler — Dynamic Priority Scheduler for Cognitive Phases.

Replaces the fixed-divisor cadence in CognitiveSpine with urgency-aware
scheduling.  Subscribes to the cognitive event bus and promotes phases to
URGENT when significant signals arrive, ensuring the system responds
immediately to risk breaches, DYON violations, and new research.

Priority levels (lower = more urgent):
  URGENT (0) — RISK_BREACH, governance override
  HIGH   (1) — DYON_VIOLATION, RESEARCH_COMPLETE, INDIRA_INSIGHT
  NORMAL (2) — regular cadence tick
  LOW    (3) — background consolidation

Signal → phase mapping:
  RISK_BREACH          → indira (URGENT), memory (URGENT)
  DYON_VIOLATION       → dyon (URGENT), indira (HIGH)
  DYON_SCAN_COMPLETE   → dyon (HIGH)
  RESEARCH_COMPLETE    → indira (HIGH)
  INDIRA_INSIGHT       → memory (HIGH)
  MARKET_TICK          → indira (NORMAL)

INV-15: ts_ns caller-supplied. No wall-clock reads.
B1: state.* and runtime.* imports only.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

# How many ticks an urgency boost decays over (after signal, phase stays boosted)
_URGENCY_DECAY_TICKS = 3


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SchedulePlan:
    """Which phases to run this tick and at what priority."""

    tick_seq: int
    ts_ns: int
    phases: dict[str, int] = field(default_factory=dict)  # phase → priority (0=urgent)
    urgency_signals: list[str] = field(default_factory=list)

    def should_run(self, phase: str, normal_divisor: int) -> bool:
        """Return True if phase should run this tick."""
        if phase in self.phases:
            return True  # urgency-boosted — always run
        return self.tick_seq % normal_divisor == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick_seq": self.tick_seq,
            "urgent_phases": [p for p, pri in self.phases.items() if pri == 0],
            "high_phases": [p for p, pri in self.phases.items() if pri == 1],
            "urgency_signals": self.urgency_signals,
        }


# ---------------------------------------------------------------------------
# CognitionScheduler
# ---------------------------------------------------------------------------


class CognitionScheduler:
    """Urgency-aware scheduler for cognitive phases.

    Subscribes to the cognitive event bus.  When significant signals arrive,
    boosts the relevant phases so they run on the NEXT tick regardless of
    their normal divisor.  Urgency decays after _URGENCY_DECAY_TICKS ticks.
    """

    # channel → (phase, priority)  — what to schedule when the channel fires
    _SIGNAL_MAP: dict[str, list[tuple[str, int]]] = {
        "RISK_BREACH":       [("indira", 0), ("memory", 0), ("cogov", 0)],
        "DYON_VIOLATION":    [("dyon", 0), ("indira", 1)],
        "DYON_SCAN_COMPLETE":[("dyon", 1)],
        "RESEARCH_COMPLETE": [("indira", 1), ("memory", 1)],
        "INDIRA_INSIGHT":    [("memory", 1)],
        "MARKET_TICK":       [("indira", 2)],
        "DYON_PROPOSAL":     [("dyon", 1), ("cogov", 1)],
    }

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._tick_seq = 0
        # phase → (priority, expires_at_tick)
        self._urgency: dict[str, tuple[int, int]] = {}
        self._signal_log: list[str] = []  # last 20 signals for snapshot

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
                if name in self._SIGNAL_MAP:
                    _ch = ch  # capture for closure
                    _name = name
                    bus.subscribe(ch, lambda payload, n=_name: self._on_signal(n, payload))
            _logger.info("CognitionScheduler: subscribed to %d channels", len(self._SIGNAL_MAP))
        except Exception as exc:
            _logger.debug("CognitionScheduler.activate error: %s", exc)

    def plan(self, ts_ns: int) -> SchedulePlan:
        """Compute the schedule plan for the current tick."""
        with self._lock:
            self._tick_seq += 1
            seq = self._tick_seq
            # Collect active urgency boosts (not yet decayed)
            phases: dict[str, int] = {}
            expired = []
            for phase, (priority, expires) in self._urgency.items():
                if seq <= expires:
                    phases[phase] = priority
                else:
                    expired.append(phase)
            for p in expired:
                del self._urgency[p]
            signals = list(self._signal_log)

        return SchedulePlan(tick_seq=seq, ts_ns=ts_ns, phases=phases, urgency_signals=signals)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active": self._active,
                "tick_seq": self._tick_seq,
                "active_boosts": {
                    phase: {"priority": pri, "expires_at": exp}
                    for phase, (pri, exp) in self._urgency.items()
                },
                "recent_signals": list(self._signal_log),
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_signal(self, channel_name: str, payload: dict[str, Any]) -> None:
        """Called when an event bus channel fires."""
        mappings = self._SIGNAL_MAP.get(channel_name, [])
        with self._lock:
            seq = self._tick_seq
            for phase, priority in mappings:
                existing = self._urgency.get(phase)
                if existing is None or priority < existing[0]:
                    self._urgency[phase] = (priority, seq + _URGENCY_DECAY_TICKS)
            self._signal_log.append(channel_name)
            if len(self._signal_log) > 20:
                self._signal_log = self._signal_log[-20:]
        _logger.debug("CognitionScheduler: signal %s → boosted %d phases", channel_name, len(mappings))


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_scheduler: CognitionScheduler | None = None
_scheduler_lock = threading.Lock()


def get_cognition_scheduler() -> CognitionScheduler:
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None:
            _scheduler = CognitionScheduler()
    return _scheduler


__all__ = [
    "CognitionScheduler",
    "SchedulePlan",
    "get_cognition_scheduler",
]
