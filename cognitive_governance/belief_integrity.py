"""
cognitive_governance/belief_integrity.py
DIX VISION v42.2 — Belief Integrity Guard

Validates that belief updates are:
  1. Calibrated  — confidence correlates with historical accuracy (ECE < threshold)
  2. Causal      — confidence changes have cited evidence, not magical jumps
  3. Bounded     — confidence stays in [0, 1] with meaningful resolution

ECE (Expected Calibration Error) is computed over a rolling window of
(confidence, correct) pairs. A system that is 80% confident should be
right ~80% of the time. Systematic overconfidence or underconfidence
are both integrity violations.

Magical jump detection: a belief whose confidence changes by > JUMP_THRESHOLD
without any new evidence citation is flagged as MAGICAL_BELIEF_JUMP.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from typing import Any

from core.contracts.cognitive_governance import (
    BeliefIntegrityReport,
    CognitiveSeverity,
    CognitiveViolationKind,
)
from state.ledger.event_store import append_event

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ECE_WARNING_THRESHOLD = 0.15
ECE_CRITICAL_THRESHOLD = 0.30
JUMP_THRESHOLD = 0.40

_NUM_BINS = 10  # bins for ECE calibration diagram


class BeliefIntegrityGuard:
    """
    Rolling belief calibration guard.

    Maintains a deque of (confidence, correct) tuples and computes
    Expected Calibration Error (ECE) across them. Also checks single-update
    magical jumps and emits COGOV_BELIEF_INTEGRITY_REPORT events on violations.
    """

    def __init__(self) -> None:
        self._window: deque[tuple[float, bool]] = deque(maxlen=500)
        self._pending: dict[str, dict[str, Any]] = {}  # prediction_id → meta
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_prediction(
        self,
        prediction_id: str,
        confidence: float,
        source: str,
        evidence_ids: list[str],
    ) -> None:
        """Register a pending prediction before its outcome is known."""
        confidence = max(0.0, min(1.0, confidence))
        with self._lock:
            self._pending[prediction_id] = {
                "confidence": confidence,
                "source": source,
                "evidence_ids": list(evidence_ids),
            }

    def record_outcome(self, prediction_id: str, correct: bool) -> None:
        """
        Record whether a prediction was correct.

        Updates the rolling ECE window and emits a
        COGOV_BELIEF_INTEGRITY_REPORT event if calibration thresholds
        are breached.
        """
        with self._lock:
            meta = self._pending.pop(prediction_id, None)
            if meta is None:
                return
            confidence = meta["confidence"]
            self._window.append((confidence, correct))
            ece = self._compute_ece()

        # Determine severity and emit event if ECE is notable
        violations: list[CognitiveViolationKind] = []
        severity = CognitiveSeverity.INFO

        if ece >= ECE_CRITICAL_THRESHOLD:
            severity = CognitiveSeverity.CRITICAL
            violations.append(CognitiveViolationKind.CALIBRATION_DRIFT)
        elif ece >= ECE_WARNING_THRESHOLD:
            severity = CognitiveSeverity.WARNING
            violations.append(CognitiveViolationKind.CALIBRATION_DRIFT)

        passed = len(violations) == 0

        if not passed:
            import time
            ts_ns = time.time_ns()
            append_event(
                "GOVERNANCE",
                "COGOV_BELIEF_INTEGRITY_REPORT",
                "cognitive_governance.belief_integrity",
                {
                    "prediction_id": prediction_id,
                    "correct": correct,
                    "ece": ece,
                    "severity": severity.value,
                    "violations": [v.value for v in violations],
                    "window_size": len(self._window),
                },
            )

    def check_belief_update(
        self,
        belief_id: str,
        confidence: float,
        prev_confidence: float,
        evidence_ids: list[str],
        source: str,
    ) -> BeliefIntegrityReport:
        """
        Validate a belief-confidence update before it is applied.

        Returns a BeliefIntegrityReport. Callers MUST check report.passed
        before applying the update.
        """
        import time
        ts_ns = time.time_ns()

        confidence = max(0.0, min(1.0, confidence))
        prev_confidence = max(0.0, min(1.0, prev_confidence))
        delta = abs(confidence - prev_confidence)

        violations: list[CognitiveViolationKind] = []
        severity = CognitiveSeverity.INFO
        detail_parts: list[str] = []

        # Check 1: magical jump without evidence
        if delta > JUMP_THRESHOLD and len(evidence_ids) == 0:
            violations.append(CognitiveViolationKind.MAGICAL_BELIEF_JUMP)
            detail_parts.append(
                f"confidence delta={delta:.3f} > JUMP_THRESHOLD={JUMP_THRESHOLD} "
                f"with no evidence cited"
            )

        # Check 2: overconfidence (confidence = 1.0 exactly is suspicious)
        if confidence >= 1.0:
            violations.append(CognitiveViolationKind.OVERCONFIDENCE)
            detail_parts.append("confidence==1.0 is an integrity violation (perfect certainty)")

        # Check 3: current ECE
        with self._lock:
            ece = self._compute_ece()

        if ece >= ECE_CRITICAL_THRESHOLD:
            violations.append(CognitiveViolationKind.CALIBRATION_DRIFT)
            detail_parts.append(f"ECE={ece:.3f} >= CRITICAL threshold {ECE_CRITICAL_THRESHOLD}")
        elif ece >= ECE_WARNING_THRESHOLD:
            violations.append(CognitiveViolationKind.CALIBRATION_DRIFT)
            detail_parts.append(f"ECE={ece:.3f} >= WARNING threshold {ECE_WARNING_THRESHOLD}")

        # Determine severity
        if CognitiveViolationKind.CALIBRATION_DRIFT in violations and ece >= ECE_CRITICAL_THRESHOLD:
            severity = CognitiveSeverity.CRITICAL
        elif CognitiveViolationKind.OVERCONFIDENCE in violations:
            severity = CognitiveSeverity.HIGH
        elif violations:
            severity = CognitiveSeverity.WARNING

        passed = len(violations) == 0
        detail = "; ".join(detail_parts) if detail_parts else "OK"

        report = BeliefIntegrityReport(
            ts_ns=ts_ns,
            belief_id=belief_id,
            source=source,
            passed=passed,
            severity=severity,
            violations=tuple(violations),
            confidence_score=confidence,
            calibration_error=ece,
            detail=detail,
        )

        if not passed:
            append_event(
                "GOVERNANCE",
                "COGOV_BELIEF_INTEGRITY_REPORT",
                "cognitive_governance.belief_integrity",
                {
                    "belief_id": belief_id,
                    "source": source,
                    "passed": passed,
                    "severity": severity.value,
                    "violations": [v.value for v in violations],
                    "confidence": confidence,
                    "prev_confidence": prev_confidence,
                    "delta": delta,
                    "ece": ece,
                    "evidence_count": len(evidence_ids),
                    "detail": detail,
                },
            )

        return report

    @property
    def get_ece(self) -> float:
        """Current ECE over the rolling window."""
        with self._lock:
            return self._compute_ece()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_ece(self) -> float:
        """
        Compute Expected Calibration Error using equal-width binning.

        ECE = Σ_b (|b| / N) × |acc(b) - conf(b)|

        where b is a confidence bin, acc(b) is the fraction of correct
        predictions in that bin, and conf(b) is the mean confidence in
        that bin.
        """
        samples = list(self._window)
        n = len(samples)
        if n == 0:
            return 0.0

        bin_width = 1.0 / _NUM_BINS
        ece = 0.0

        for bin_idx in range(_NUM_BINS):
            low = bin_idx * bin_width
            high = low + bin_width
            # Include upper boundary in last bin
            if bin_idx == _NUM_BINS - 1:
                high = 1.0 + 1e-9

            in_bin = [(conf, corr) for conf, corr in samples if low <= conf < high]
            if not in_bin:
                continue

            b_n = len(in_bin)
            acc = sum(1 for _, corr in in_bin if corr) / b_n
            conf_mean = sum(conf for conf, _ in in_bin) / b_n
            ece += (b_n / n) * abs(acc - conf_mean)

        return ece


# ---------------------------------------------------------------------------
# Singleton factory (same pattern as governance/risk_engine.py)
# ---------------------------------------------------------------------------

_instance: BeliefIntegrityGuard | None = None
_lock = threading.Lock()


def get_belief_integrity_guard() -> BeliefIntegrityGuard:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = BeliefIntegrityGuard()
    return _instance


__all__ = ["BeliefIntegrityGuard", "get_belief_integrity_guard"]
