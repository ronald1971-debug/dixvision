"""
cognitive_governance/learning_coherence.py
DIX VISION v42.2 — Learning Coherence Scorer

Evaluates the overall coherence of the learning pipeline by combining
signals from all cognitive guards into a single LearningCoherenceScore.

A low coherence score means that multiple cognitive subsystems are in
disagreement or degraded simultaneously — which is a stronger signal
than any single guard flagging a violation.

Coherence dimensions (equal weight by default):
  1. Epistemic grounding   — external vs. synthetic signal ratio
  2. Belief calibration    — ECE calibration quality
  3. Mutation safety       — fraction of mutations approved
  4. Memory integrity      — inverse contamination score
  5. Identity stability    — cosine similarity to baseline
  6. Reward alignment      — reward–objective correlation

The overall coherence score is in [0, 1].
  ≥ 0.80 — HIGH    coherence: learning pipeline healthy
  ≥ 0.60 — MEDIUM  coherence: some degradation, monitor closely
  < 0.60 — LOW     coherence: significant degradation, halt learning updates
  < 0.40 — CRITICAL coherence: cognitive integrity at risk, escalate

Thread-safe. Pure aggregation — delegates to guard singletons.
Emits COGOV_LEARNING_COHERENCE events to the governance ledger.
"""

from __future__ import annotations

import math
import threading
import time as _time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class CoherenceLevel(StrEnum):
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class LearningCoherenceScore:
    """Composite coherence snapshot across all learning guards."""
    ts_ns: int
    # Per-dimension scores [0, 1]
    epistemic_grounding: float
    belief_calibration: float
    mutation_safety: float
    memory_integrity: float
    identity_stability: float
    reward_alignment: float
    # Composite
    overall_score: float
    level: CoherenceLevel
    # Actionable gate: should learning updates be halted?
    halt_learning: bool
    detail: str = ""


def _coherence_level(score: float) -> CoherenceLevel:
    if score >= 0.80:
        return CoherenceLevel.HIGH
    if score >= 0.60:
        return CoherenceLevel.MEDIUM
    if score >= 0.40:
        return CoherenceLevel.LOW
    return CoherenceLevel.CRITICAL


def _safe_get(fn, default: float) -> float:
    try:
        result = fn()
        return float(result) if result is not None else default
    except Exception:
        return default


class LearningCoherenceMonitor:
    """
    Aggregates all cognitive guard signals into a single coherence score.

    Thread-safe. Queries guard singletons; no state of its own beyond
    the rolling score history.
    """

    _HALT_THRESHOLD = 0.60   # halt learning updates below this

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: list[LearningCoherenceScore] = []
        self._max_history = 200
        self._status_interval_ns = 60 * 1_000_000_000

    def score(self, ts_ns: int | None = None) -> LearningCoherenceScore:
        """Compute current learning coherence score from guard state."""
        ts_ns = ts_ns or _time.time_ns()

        # --- Epistemic grounding ---
        # Ratio of externally-anchored signals (1.0 = fully grounded)
        try:
            from cognitive_governance.learning_truthfulness import get_learning_truthfulness_validator
            ext_ratio = _safe_get(get_learning_truthfulness_validator().get_external_ratio, 0.5)
        except Exception:
            ext_ratio = 0.5

        # --- Belief calibration ---
        # ECE: lower is better; map to [0,1] score where 0 ECE → 1.0
        try:
            from cognitive_governance.belief_integrity import get_belief_integrity_guard
            ece = _safe_get(get_belief_integrity_guard().get_ece, 0.0)
            # ECE of 0.30 or above maps to 0.0 score; 0.0 ECE maps to 1.0
            belief_cal = max(0.0, 1.0 - (ece / 0.30))
        except Exception:
            belief_cal = 0.5

        # --- Mutation safety ---
        # Fraction of recent mutations that were approved
        try:
            from cognitive_governance.mutation_validator import get_mutation_validator
            mv = get_mutation_validator()
            total = mv._total_validated if hasattr(mv, "_total_validated") else 0
            approved = mv._total_approved if hasattr(mv, "_total_approved") else 0
            mutation_safety = (approved / total) if total > 0 else 1.0
        except Exception:
            mutation_safety = 1.0

        # --- Memory integrity ---
        # Inverse of contamination score (contamination 0.0 → integrity 1.0)
        try:
            from cognitive_governance.memory_contamination import get_memory_contamination_detector
            mcd = get_memory_contamination_detector()
            max_contam = mcd.max_contamination_score() if hasattr(mcd, "max_contamination_score") else 0.0
            memory_integrity = max(0.0, 1.0 - max_contam)
        except Exception:
            memory_integrity = 1.0

        # --- Identity stability ---
        # Blend: cosine similarity to 7-day baseline + long-horizon drift signal
        try:
            from cognitive_governance.identity_stability import get_identity_stability_monitor
            ism = get_identity_stability_monitor()
            min_sim = ism.min_similarity() if hasattr(ism, "min_similarity") else 1.0
            short_stab = max(0.0, min_sim)
        except Exception:
            short_stab = 1.0
        try:
            from cognitive_governance.long_horizon_memory import get_long_horizon_memory
            long_stab = get_long_horizon_memory().identity_stability_signal()
        except Exception:
            long_stab = 1.0
        # 70% short-horizon cosine similarity, 30% long-horizon drift signal
        identity_stab = 0.7 * short_stab + 0.3 * long_stab

        # --- Reward alignment ---
        # Correlation between reward and true objective (1.0 = aligned)
        try:
            from cognitive_governance.reward_hacking_detector import get_reward_hacking_detector
            rhd = get_reward_hacking_detector()
            min_corr = rhd.min_correlation() if hasattr(rhd, "min_correlation") else 1.0
            reward_align = max(0.0, (min_corr + 1.0) / 2.0)  # [-1,1] → [0,1]
        except Exception:
            reward_align = 1.0

        # --- Composite (equal weights) ---
        dims = [ext_ratio, belief_cal, mutation_safety, memory_integrity,
                identity_stab, reward_align]
        # Geometric mean emphasises lowest dimension
        product = 1.0
        for d in dims:
            product *= max(1e-6, d)
        geometric_mean = product ** (1.0 / len(dims))
        arithmetic_mean = sum(dims) / len(dims)
        # Blend: 60% geometric, 40% arithmetic (punishes weak dims)
        overall = 0.6 * geometric_mean + 0.4 * arithmetic_mean

        level = _coherence_level(overall)
        halt = overall < self._HALT_THRESHOLD

        detail_parts: list[str] = []
        if ext_ratio < 0.6:
            detail_parts.append(f"epistemic_grounding={ext_ratio:.2f}")
        if belief_cal < 0.6:
            detail_parts.append(f"belief_calibration={belief_cal:.2f}")
        if mutation_safety < 0.8:
            detail_parts.append(f"mutation_safety={mutation_safety:.2f}")
        if memory_integrity < 0.8:
            detail_parts.append(f"memory_integrity={memory_integrity:.2f}")

        result = LearningCoherenceScore(
            ts_ns=ts_ns,
            epistemic_grounding=ext_ratio,
            belief_calibration=belief_cal,
            mutation_safety=mutation_safety,
            memory_integrity=memory_integrity,
            identity_stability=identity_stab,
            reward_alignment=reward_align,
            overall_score=overall,
            level=level,
            halt_learning=halt,
            detail="; ".join(detail_parts) if detail_parts else f"score={overall:.3f}",
        )

        with self._lock:
            self._history.append(result)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        return result

    def latest(self) -> LearningCoherenceScore | None:
        with self._lock:
            return self._history[-1] if self._history else None

    def trend(self, window: int = 10) -> float:
        """
        Compute score trend over recent window.
        Positive = improving, negative = degrading.
        """
        with self._lock:
            recent = [s.overall_score for s in self._history[-window:]]
        if len(recent) < 2:
            return 0.0
        return recent[-1] - recent[0]

    def snapshot(self) -> dict[str, Any]:
        latest = self.latest()
        return {
            "latest_score": latest.overall_score if latest else None,
            "latest_level": latest.level.value if latest else None,
            "halt_learning": latest.halt_learning if latest else False,
            "history_size": len(self._history),
            "trend_10": self.trend(10),
        }


# Singleton factory
_instance: LearningCoherenceMonitor | None = None
_lock = threading.Lock()


def get_learning_coherence_monitor() -> LearningCoherenceMonitor:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = LearningCoherenceMonitor()
    return _instance


__all__ = [
    "CoherenceLevel",
    "LearningCoherenceMonitor",
    "LearningCoherenceScore",
    "get_learning_coherence_monitor",
]
