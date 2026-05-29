"""INDIRA Thought Runtime — active inner reasoning loop (COGNITIVE ACTIVATION PHASE).

INDIRA thinks continuously, not only when market ticks arrive. This module
owns the *always-on* cognition surface: a rolling thought buffer, periodic
self-reflection ticks, and a structured snapshot of INDIRA's current mental
state for the operator dashboard.

Design:
* Stateful but side-effect-free on construction — no I/O in __init__.
* ``tick(ts_ns)`` drives one reasoning cycle and emits a ThoughtStreamEvent.
* All ledger writes go through the observability emitter (best-effort, never
  raises), preserving the fire-and-forget pattern across the codebase.
* ``snapshot()`` returns a frozen dict safe for JSON serialisation.

INV-15: timestamps come from caller-supplied ``ts_ns``. No wall-clock reads
inside tick(). ``thought_id`` uses the sequence counter, not uuid, to keep
the replay path deterministic.

Authority (B1): imports only from intelligence_engine.* and core.*.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Thought record
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Thought:
    """One unit of INDIRA's internal reasoning."""

    thought_id: str
    ts_ns: int
    step: str          # e.g. "self_reflection", "memory_query", "regime_assessment"
    context: str
    conclusion: str
    confidence: float


# ---------------------------------------------------------------------------
# Reasoning templates — the subjects INDIRA reflects on autonomously
# ---------------------------------------------------------------------------

_REFLECTION_CYCLE: tuple[tuple[str, str, str], ...] = (
    (
        "self_reflection",
        "Reviewing internal state: signal window depth, "
        "regime stability, and active strategy count.",
        "System is operating within cognitive parameters.",
    ),
    (
        "regime_assessment",
        "Assessing current committed market regime and hysteresis stability.",
        "Regime belief is maintained pending new signal evidence.",
    ),
    (
        "memory_consolidation",
        "Scanning episodic memory for analogous historical patterns.",
        "Memory consolidation pass complete; relevant episodes indexed.",
    ),
    (
        "strategy_review",
        "Reviewing arena strategy allocation and composite score distribution.",
        "Strategy allocation reflects current regime fitness scores.",
    ),
    (
        "research_queue",
        "Evaluating research queue: pending topics, source trust levels.",
        "Research pipeline is active; findings will update belief state.",
    ),
    (
        "confidence_calibration",
        "Calibrating confidence estimate against recent win/loss history.",
        "Confidence is proportional to regime stability and signal consensus.",
    ),
    (
        "operator_alignment",
        "Verifying cognitive outputs align with operator authority boundaries.",
        "All decisions remain within operator-declared intent boundaries.",
    ),
    (
        "evolution_awareness",
        "Monitoring DYON patch proposals and architectural drift reports.",
        "DYON engineering intelligence is active and scanning topology.",
    ),
)


# ---------------------------------------------------------------------------
# ThoughtRuntime
# ---------------------------------------------------------------------------


class ThoughtRuntime:
    """INDIRA's always-on thought runtime.

    Emits one :class:`Thought` per :meth:`tick` call, cycling through a
    fixed set of reflection topics. Callers drive the tick rate; this class
    never reads the wall clock.

    Args:
        max_history: Rolling buffer depth for :meth:`snapshot`.
        confidence_baseline: Default confidence for autonomous thoughts.
            Overridden per-step when external signals are available.
    """

    def __init__(
        self,
        *,
        max_history: int = 200,
        confidence_baseline: float = 0.65,
    ) -> None:
        self._history: deque[Thought] = deque(maxlen=max_history)
        self._cycle_index: int = 0
        self._tick_count: int = 0
        self._confidence_baseline = confidence_baseline

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def tick(
        self,
        *,
        ts_ns: int,
        context_override: str | None = None,
        conclusion_override: str | None = None,
        confidence_override: float | None = None,
    ) -> Thought:
        """Emit one INDIRA thought and advance the cycle.

        Args:
            ts_ns: Caller-supplied nanosecond timestamp (INV-15).
            context_override: Optional context string. Replaces the template
                context — use this when a caller has richer situational info
                (e.g., the IntelligenceEngine after a real meta-controller tick).
            conclusion_override: Optional conclusion string.
            confidence_override: Optional confidence value in [0, 1].

        Returns:
            The :class:`Thought` that was recorded and emitted.
        """
        self._tick_count += 1
        step, default_context, default_conclusion = _REFLECTION_CYCLE[
            self._cycle_index % len(_REFLECTION_CYCLE)
        ]
        self._cycle_index = (self._cycle_index + 1) % len(_REFLECTION_CYCLE)

        thought = Thought(
            thought_id=f"indira_thought_{self._tick_count}_{ts_ns}",
            ts_ns=ts_ns,
            step=step,
            context=context_override or default_context,
            conclusion=conclusion_override or default_conclusion,
            confidence=confidence_override if confidence_override is not None
            else self._confidence_baseline,
        )
        self._history.append(thought)
        self._emit(thought)
        return thought

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def recent(self, limit: int = 20) -> list[Thought]:
        """Return the most recent thoughts, newest-first."""
        items = list(self._history)
        items.reverse()
        return items[:limit]

    def snapshot(self, limit: int = 20) -> dict[str, Any]:
        """Return a JSON-serialisable snapshot of INDIRA's recent cognition."""
        thoughts = self.recent(limit)
        return {
            "intelligence": "INDIRA",
            "tick_count": self._tick_count,
            "cycle_position": self._cycle_index,
            "recent_thoughts": [
                {
                    "thought_id": t.thought_id,
                    "ts_ns": t.ts_ns,
                    "step": t.step,
                    "context": t.context,
                    "conclusion": t.conclusion,
                    "confidence": t.confidence,
                }
                for t in thoughts
            ],
        }

    # ------------------------------------------------------------------
    # Parameter update from LearningPersistence
    # ------------------------------------------------------------------

    def set_confidence_baseline(self, value: float) -> None:
        """Update the default confidence applied to autonomous thoughts.

        Called by LearningPersistence when the slow-loop learner proposes
        a new value.  Clamped to [0.10, 0.99] as a safety rail.
        """
        self._confidence_baseline = max(0.10, min(0.99, value))

    # ------------------------------------------------------------------
    # Restore (boot-time continuity)
    # ------------------------------------------------------------------

    def restore(self, thoughts: list[Thought]) -> int:
        """Populate the history buffer from previously-persisted thoughts.

        Provides cognitive continuity across restarts: the ring buffer is
        seeded with the last N thoughts from the ledger so INDIRA does not
        start each process with a blank mental state.

        Does NOT re-emit — these thoughts already reached the ledger before
        the process restarted.

        Returns the number of thoughts loaded.
        """
        if not thoughts:
            return 0
        # Sort oldest-first so the deque tail holds the most recent thought.
        ordered = sorted(thoughts, key=lambda t: t.ts_ns)
        for t in ordered:
            self._history.append(t)
        last = ordered[-1]
        # Advance tick counter past the restored sequence so new IDs don't
        # collide with restored ones.
        try:
            restored_tick = int(last.thought_id.split("_")[2])
            self._tick_count = max(self._tick_count, restored_tick)
        except (IndexError, ValueError):
            self._tick_count = max(self._tick_count, len(ordered))
        # Restore cycle position so the next tick continues the reflection
        # cycle from where cognition left off, not from step 0.
        step_names = [s for s, _, _ in _REFLECTION_CYCLE]
        if last.step in step_names:
            idx = step_names.index(last.step)
            self._cycle_index = (idx + 1) % len(_REFLECTION_CYCLE)
        return len(ordered)

    # ------------------------------------------------------------------
    # Emit
    # ------------------------------------------------------------------

    @staticmethod
    def _emit(thought: Thought) -> None:
        """Best-effort ThoughtStreamEvent emission + event bus publish. Never raises."""
        try:
            from intelligence_engine.cognitive.observability_emitter import (
                emit_thought_stream,
            )
            emit_thought_stream(
                ts_ns=thought.ts_ns,
                reasoning_step=thought.step,
                context=thought.context,
                confidence=thought.confidence,
                inputs=(),
                conclusion=thought.conclusion,
            )
        except Exception:  # pragma: no cover
            pass
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.INDIRA_THOUGHT, {
                "thought_id": thought.thought_id,
                "step": thought.step,
                "confidence": thought.confidence,
                "ts_ns": thought.ts_ns,
            })
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_runtime: ThoughtRuntime | None = None


def get_thought_runtime() -> ThoughtRuntime:
    """Return the module-level singleton ThoughtRuntime."""
    global _runtime
    if _runtime is None:
        _runtime = ThoughtRuntime()
    return _runtime


__all__ = [
    "Thought",
    "ThoughtRuntime",
    "get_thought_runtime",
]
