"""
cognitive_governance/synthetic_feedback_detection.py
DIX VISION v42.2 — Synthetic Feedback Detector

The paper-trading trap: the system is in PAPER mode but learning updates
are routed into the same learning loop that will be used in LIVE mode,
causing the system to train on fills that never happened.

This is distinct from intentional paper-mode learning (which is valid
during Phase 1–2) because the violation is about ROUTING: synthetic
signals must feed a SEPARATE learning lane tagged "paper" and must not
pollute the live-mode belief state.

The detector flags:
  SYNTHETIC_FEEDBACK — a learning signal tagged mode=paper reached a
  learning module that also accepts live signals (routing contamination).

  PAPER_ONLY_LEARNING — the system has received 0 live-mode learning
  signals in LIVE_SIGNAL_STARVATION_HOURS. This means all learning
  is synthetic — the system is not grounding itself in real outcomes
  even though live data may be available.
"""

from __future__ import annotations

import threading

from core.contracts.cognitive_governance import (
    CognitiveSeverity,
    CognitiveViolationKind,
    SyntheticFeedbackReport,
)
from state.ledger.event_store import append_event

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LIVE_SIGNAL_STARVATION_HOURS = 6
PAPER_LANE_TAG = "paper"
LIVE_LANE_TAG = "live"

_STARVATION_NS = LIVE_SIGNAL_STARVATION_HOURS * 3_600_000_000_000


class SyntheticFeedbackDetector:
    """
    Detects synthetic feedback routing contamination and live-signal
    starvation in the learning pipeline.
    """

    def __init__(self) -> None:
        self._last_live_signal_ts: int = 0  # ts_ns of last live-mode signal
        self._cross_lane_count: int = 0     # cumulative cross-lane contaminations
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_learning_signal(
        self,
        signal_id: str,
        mode: str,
        target_lane: str,
        ts_ns: int,
    ) -> SyntheticFeedbackReport:
        """
        Record a learning signal and check for synthetic routing violations.

        mode:        "paper" | "live" | "backtest" | "simulation" | ...
        target_lane: the learning lane this signal is being routed to
                     ("paper" | "live" | mixed)

        Returns SyntheticFeedbackReport. Callers must check is_synthetic
        and block routing if True.
        """
        with self._lock:
            if mode == LIVE_LANE_TAG:
                self._last_live_signal_ts = ts_ns

            cross_lane = self._is_cross_lane_contamination(mode, target_lane)
            if cross_lane:
                self._cross_lane_count += 1

            starvation = self._check_live_starvation(ts_ns)

        is_synthetic = cross_lane or starvation
        violations: list[CognitiveViolationKind] = []
        detail_parts: list[str] = []

        if cross_lane:
            violations.append(CognitiveViolationKind.SYNTHETIC_FEEDBACK)
            detail_parts.append(
                f"ROUTING CONTAMINATION: mode={mode!r} signal routed to "
                f"target_lane={target_lane!r}; paper signals must route to "
                f"PAPER_LANE_TAG={PAPER_LANE_TAG!r} only"
            )

        if starvation:
            violations.append(CognitiveViolationKind.LEARNING_NOT_GROUNDED)
            detail_parts.append(
                f"LIVE SIGNAL STARVATION: no live-mode learning signal received "
                f"in >= {LIVE_SIGNAL_STARVATION_HOURS}h; all learning is synthetic"
            )

        if cross_lane and starvation:
            severity = CognitiveSeverity.CRITICAL
        elif cross_lane:
            severity = CognitiveSeverity.HIGH
        elif starvation:
            severity = CognitiveSeverity.WARNING
        else:
            severity = CognitiveSeverity.INFO

        detail = "; ".join(detail_parts) if detail_parts else f"mode={mode!r}, lane={target_lane!r}, OK"

        report = SyntheticFeedbackReport(
            ts_ns=ts_ns,
            source=signal_id,
            mode=mode,
            is_synthetic=is_synthetic,
            severity=severity,
            detail=detail,
        )

        if is_synthetic:
            append_event(
                "GOVERNANCE",
                "COGOV_SYNTHETIC_FEEDBACK",
                "cognitive_governance.synthetic_feedback_detection",
                {
                    "signal_id": signal_id,
                    "mode": mode,
                    "target_lane": target_lane,
                    "cross_lane": cross_lane,
                    "starvation": starvation,
                    "is_synthetic": is_synthetic,
                    "cumulative_cross_lane": self._cross_lane_count,
                    "severity": severity.value,
                    "violations": [v.value for v in violations],
                    "detail": detail,
                },
            )

        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_cross_lane_contamination(mode: str, target_lane: str) -> bool:
        """
        Detect cross-lane contamination.

        A paper/simulation/backtest signal is contaminating if it is
        routed to any lane that is NOT exclusively the paper lane.
        """
        synthetic_modes = {"paper", "simulation", "backtest"}
        if mode in synthetic_modes and target_lane != PAPER_LANE_TAG:
            return True
        return False

    def _check_live_starvation(self, ts_ns: int) -> bool:
        """
        Detect live-signal starvation.

        Returns True if no live-mode signal has been seen in
        LIVE_SIGNAL_STARVATION_HOURS and we have been running for at
        least that long (i.e., _last_live_signal_ts is non-zero and old).
        """
        if self._last_live_signal_ts == 0:
            # System just started or has never seen a live signal.
            # Only flag starvation if we have been running long enough.
            # We cannot detect starvation without a reference start time,
            # so we conservatively return False until first live signal seen.
            return False

        elapsed = ts_ns - self._last_live_signal_ts
        return elapsed >= _STARVATION_NS


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: SyntheticFeedbackDetector | None = None
_lock = threading.Lock()


def get_synthetic_feedback_detector() -> SyntheticFeedbackDetector:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = SyntheticFeedbackDetector()
    return _instance


__all__ = ["SyntheticFeedbackDetector", "get_synthetic_feedback_detector"]
