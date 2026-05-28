"""
cognitive_governance/epistemic_drift.py
DIX VISION v42.2 — Epistemic Drift Monitor

Tracks the accumulated divergence between what the system predicted
and what was actually observed. This is the "intellectual drawdown"
analogue — the cognitive equivalent of realised PnL vs. expected PnL.

The drift score is computed as a rolling Mean Absolute Error over
(predicted_value, observed_value) pairs normalised to [0, 1]:

    drift_score = mean(|predicted - observed|) / NORMALISATION_SCALE

Thresholds:
    < WARNING_THRESHOLD  →  INFO (healthy calibration)
    ≥ WARNING_THRESHOLD  →  WARNING (EPISTEMIC_DRIFT_WARNING)
    ≥ CRITICAL_THRESHOLD →  CRITICAL (EPISTEMIC_DRIFT_CRITICAL)
                            triggers governance notification

On CRITICAL: the monitor emits a governance event suggesting the system
should pause learning updates and increase external grounding (more live
data, less synthetic). It does NOT block execution — that is Governance's
decision.
"""

from __future__ import annotations

import threading
import time as _time
from collections import deque

from core.contracts.cognitive_governance import (
    CognitiveSeverity,
    CognitiveViolationKind,
    EpistemicDriftReport,
)
from state.ledger.event_store import append_event

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_SIZE = 500
WARNING_THRESHOLD = 0.25
CRITICAL_THRESHOLD = 0.50
NORMALISATION_SCALE = 1.0


class EpistemicDriftMonitor:
    """
    Monitors rolling mean absolute error between predicted and observed
    values as a proxy for epistemic calibration health.
    """

    def __init__(self) -> None:
        # Rolling window of (predicted, observed) float pairs
        self._window: deque[tuple[float, float]] = deque(maxlen=WINDOW_SIZE)
        # Pending predictions awaiting outcome: prediction_id → (predicted, ts_ns)
        self._pending: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_prediction(self, prediction_id: str, predicted: float, ts_ns: int) -> None:
        """Register a pending prediction before its outcome arrives."""
        with self._lock:
            self._pending[prediction_id] = (predicted, ts_ns)

    def record_outcome(
        self, prediction_id: str, observed: float, ts_ns: int
    ) -> EpistemicDriftReport:
        """
        Record the observed outcome for a pending prediction.

        Computes the updated drift score and emits COGOV_EPISTEMIC_DRIFT
        to the governance ledger if any threshold is breached.
        Returns an EpistemicDriftReport.
        """
        with self._lock:
            pending = self._pending.pop(prediction_id, None)
            if pending is None:
                # Outcome for unknown prediction — record as (0.5, observed)
                predicted = 0.5
                pred_ts_ns = ts_ns
            else:
                predicted, pred_ts_ns = pending

            self._window.append((predicted, observed))
            drift_score = self._compute_drift_score()
            n_samples = len(self._window)
            window_ns = ts_ns - pred_ts_ns if ts_ns > pred_ts_ns else 0
            mae = drift_score * NORMALISATION_SCALE
            accumulated_error = mae * n_samples

        # Determine severity
        violations: list[CognitiveViolationKind] = []
        threshold_breached = False
        severity = CognitiveSeverity.INFO

        if drift_score >= CRITICAL_THRESHOLD:
            violations.append(CognitiveViolationKind.EPISTEMIC_DRIFT_CRITICAL)
            severity = CognitiveSeverity.CRITICAL
            threshold_breached = True
        elif drift_score >= WARNING_THRESHOLD:
            violations.append(CognitiveViolationKind.EPISTEMIC_DRIFT_WARNING)
            severity = CognitiveSeverity.WARNING
            threshold_breached = True

        detail_parts: list[str] = []
        if drift_score >= CRITICAL_THRESHOLD:
            detail_parts.append(
                f"CRITICAL: drift_score={drift_score:.4f} >= {CRITICAL_THRESHOLD}; "
                "recommend pausing learning updates and increasing external grounding"
            )
        elif drift_score >= WARNING_THRESHOLD:
            detail_parts.append(
                f"WARNING: drift_score={drift_score:.4f} >= {WARNING_THRESHOLD}"
            )
        detail = "; ".join(detail_parts) if detail_parts else f"drift_score={drift_score:.4f}, OK"

        report = EpistemicDriftReport(
            ts_ns=ts_ns,
            window_ns=window_ns,
            drift_score=drift_score,
            mean_absolute_error=mae,
            accumulated_error=accumulated_error,
            n_samples=n_samples,
            threshold_breached=threshold_breached,
            severity=severity,
            detail=detail,
        )

        if threshold_breached:
            append_event(
                "GOVERNANCE",
                "COGOV_EPISTEMIC_DRIFT",
                "cognitive_governance.epistemic_drift",
                {
                    "prediction_id": prediction_id,
                    "drift_score": drift_score,
                    "mae": mae,
                    "n_samples": n_samples,
                    "severity": severity.value,
                    "violations": [v.value for v in violations],
                    "detail": detail,
                },
            )

        return report

    def get_drift_score(self) -> float:
        """Return the current rolling drift score."""
        with self._lock:
            return self._compute_drift_score()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_drift_score(self) -> float:
        """
        Compute rolling MAE normalised by NORMALISATION_SCALE.

        drift_score = mean(|predicted - observed|) / NORMALISATION_SCALE
        """
        samples = list(self._window)
        if not samples:
            return 0.0
        mae = sum(abs(p - o) for p, o in samples) / len(samples)
        return min(1.0, mae / NORMALISATION_SCALE) if NORMALISATION_SCALE > 0 else 0.0


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: EpistemicDriftMonitor | None = None
_lock = threading.Lock()


def get_epistemic_drift_monitor() -> EpistemicDriftMonitor:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = EpistemicDriftMonitor()
    return _instance


__all__ = ["EpistemicDriftMonitor", "get_epistemic_drift_monitor"]
