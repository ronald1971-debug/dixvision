"""ReflectionEngine — past-thought synthesis for INDIRA (P0 Cognitive Emergence).

Every N cognitive ticks INDIRA looks back at her recent thoughts, identifies
patterns in confidence, reasoning step distribution, and conclusion themes,
then synthesises a single meta-thought that captures what she is collectively
*discovering* from her own reasoning stream.

This is not a template loop.  It reads actual historical thought records and
derives real signals from them.

Authority (B1): imports only from intelligence_engine.* and core.*.
INV-15: ts_ns is caller-supplied; no internal clock reads.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from typing import Any

_logger = logging.getLogger(__name__)

# How many recent thoughts to analyse per reflection pass
_ANALYSIS_WINDOW = 20

# Minimum thoughts required before reflection is worth emitting
_MIN_THOUGHTS = 5


class ReflectionEngine:
    """Synthesises meta-thoughts from INDIRA's recent thought history.

    Designed to be called from IndiraRuntime every N ticks
    (recommended: every 10).  Operates entirely on the Thought deque
    already held in ThoughtRuntime — no extra storage required.
    """

    def __init__(self) -> None:
        self._reflection_seq: int = 0

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    def reflect(self, thoughts: list[Any], *, ts_ns: int) -> str | None:
        """Analyse *thoughts* and emit a meta-thought if patterns found.

        Args:
            thoughts: Recent Thought records (newest-first or oldest-first;
                      order does not affect results since we aggregate).
            ts_ns:    Nanosecond timestamp for the emitted event.

        Returns:
            The synthesised reflection text, or None if too few thoughts.
        """
        if len(thoughts) < _MIN_THOUGHTS:
            return None

        window = thoughts[:_ANALYSIS_WINDOW]
        self._reflection_seq += 1

        # ---- 1. Confidence analysis ----------------------------------------
        confidences = [
            t.confidence for t in window
            if hasattr(t, "confidence") and isinstance(t.confidence, (int, float))
        ]
        mean_conf = sum(confidences) / len(confidences) if confidences else 0.5
        trend = self._confidence_trend(confidences)

        # ---- 2. Reasoning step distribution --------------------------------
        steps = [getattr(t, "step", "") for t in window if getattr(t, "step", "")]
        step_counter = Counter(steps)
        dominant_step, dom_count = step_counter.most_common(1)[0] if step_counter else ("unknown", 0)

        # ---- 3. Conclusion theme extraction --------------------------------
        conclusions = [
            getattr(t, "conclusion", "") for t in window
            if getattr(t, "conclusion", "")
        ]
        theme = self._extract_theme(conclusions)

        # ---- 4. Synthesise reflection text ---------------------------------
        trend_str = (
            "improving" if trend > 0.02 else
            "declining" if trend < -0.02 else
            "stable"
        )
        synthesis = (
            f"Reflection #{self._reflection_seq}: over {len(window)} recent cycles, "
            f"confidence is {trend_str} (mean={mean_conf:.2f}). "
            f"Dominant reasoning: '{dominant_step}' ({dom_count}/{len(window)}). "
            f"Prevailing theme: {theme}."
        )

        # ---- 5. Emit as a thought with reasoning_step='reflection' --------
        self._emit_reflection(synthesis=synthesis, confidence=mean_conf, ts_ns=ts_ns)

        return synthesis

    # ------------------------------------------------------------------
    # Analysis helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _confidence_trend(confidences: list[float]) -> float:
        """Slope of a simple linear fit to confidence values.

        Positive → improving.  Negative → declining.
        Returns 0.0 if fewer than 2 samples.
        """
        n = len(confidences)
        if n < 2:
            return 0.0
        # Simple least-squares slope: Σ(xi - x̄)(yi - ȳ) / Σ(xi - x̄)²
        x_mean = (n - 1) / 2.0
        y_mean = sum(confidences) / n
        num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(confidences))
        denom = sum((i - x_mean) ** 2 for i in range(n))
        return num / denom if abs(denom) > 1e-10 else 0.0

    @staticmethod
    def _extract_theme(conclusions: list[str]) -> str:
        """Extract the most frequent non-trivial word across conclusions."""
        _STOPWORDS = frozenset({
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "to", "of", "in", "on", "at", "for", "with", "and", "or",
            "it", "this", "that", "from", "by", "as", "not", "has",
            "have", "had", "but", "all", "no", "so", "if", "its",
            "will", "can", "may", "into", "than", "more", "within",
        })
        words: Counter[str] = Counter()
        for c in conclusions:
            for w in c.lower().split():
                w = w.strip(".,;:!?\"'()")
                if len(w) > 3 and w not in _STOPWORDS:
                    words[w] += 1
        top = words.most_common(3)
        return " / ".join(w for w, _ in top) if top else "general market cognition"

    # ------------------------------------------------------------------
    # Emission (best-effort)
    # ------------------------------------------------------------------

    @staticmethod
    def _emit_reflection(*, synthesis: str, confidence: float, ts_ns: int) -> None:
        try:
            from intelligence_engine.cognitive.observability_emitter import (
                emit_thought_stream,
            )
            emit_thought_stream(
                ts_ns=ts_ns,
                reasoning_step="reflection",
                context=f"meta-analysis of recent {_ANALYSIS_WINDOW} thoughts",
                confidence=round(max(0.0, min(1.0, confidence)), 4),
                inputs=("thought_history",),
                conclusion=synthesis,
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_engine: ReflectionEngine | None = None


def get_reflection_engine() -> ReflectionEngine:
    """Return the process-wide ReflectionEngine singleton."""
    global _engine
    if _engine is None:
        _engine = ReflectionEngine()
    return _engine


__all__ = [
    "ReflectionEngine",
    "get_reflection_engine",
]
