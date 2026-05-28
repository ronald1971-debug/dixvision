"""
cognitive_governance/learning_truthfulness.py
DIX VISION v42.2 — Learning Truthfulness Validator

Validates that learning signals are grounded in external observations,
not purely synthetic or self-generated.

A "grounded" learning signal is one that can be traced back to at least
one external truth anchor within GROUNDING_MAX_HOPS hops:
  - A real market tick from a live feed
  - A confirmed exchange fill (not paper)
  - A verified on-chain event

A "synthetic" learning signal has no such anchor within
GROUNDING_MAX_HOPS — it references only internal predictions,
other learning signals, or paper fills.

The guard tracks a rolling WINDOW_SIZE of recent signals and computes
the EXTERNAL_RATIO. If the ratio falls below TRUTHFULNESS_THRESHOLD
the system is learning from itself more than from reality.

This is distinct from the HallucinationGuard (which detects deep loop
structures). LearningTruthfulnessValidator detects the simpler case
where the MAJORITY of learning signals are synthetic, even if none of
them form explicit loops.
"""

from __future__ import annotations

import threading
from collections import deque

from core.contracts.cognitive_governance import (
    CognitiveSeverity,
    CognitiveViolationKind,
    LearningTruthfulnessReport,
)
from state.ledger.event_store import append_event

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_SIZE = 200
TRUTHFULNESS_THRESHOLD = 0.40
GROUNDING_MAX_HOPS = 3


class LearningTruthfulnessValidator:
    """
    Tracks the ratio of externally-grounded to synthetic learning signals
    over a rolling window and flags when synthetic signals dominate.
    """

    def __init__(self) -> None:
        # Rolling deque of booleans: True = grounded, False = synthetic
        self._window: deque[bool] = deque(maxlen=WINDOW_SIZE)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_learning_signal(
        self,
        signal_id: str,
        source: str,
        external_anchors: list[str],
        mode: str,
        ts_ns: int,
    ) -> LearningTruthfulnessReport:
        """
        Record a learning signal and evaluate the rolling truthfulness ratio.

        external_anchors: list of anchor identifiers (market tick IDs,
        fill IDs, on-chain event hashes) that ground this signal.
        An empty list means purely synthetic.

        Returns LearningTruthfulnessReport. Callers should log non-passed
        reports and escalate to Governance review.
        """
        grounded = self._is_grounded(external_anchors, mode)

        with self._lock:
            self._window.append(grounded)
            window_n = len(self._window)
            grounded_count = sum(1 for v in self._window if v)
            synthetic_count = window_n - grounded_count
            external_ratio = grounded_count / window_n if window_n > 0 else 1.0

        passed = external_ratio >= TRUTHFULNESS_THRESHOLD

        # Severity
        if not passed:
            if external_ratio < TRUTHFULNESS_THRESHOLD * 0.5:
                severity = CognitiveSeverity.CRITICAL
            else:
                severity = CognitiveSeverity.WARNING
        else:
            severity = CognitiveSeverity.INFO

        violations: list[CognitiveViolationKind] = []
        if not passed:
            violations.append(CognitiveViolationKind.LEARNING_NOT_GROUNDED)

        detail = (
            f"external_ratio={external_ratio:.3f} "
            f"({'PASS' if passed else 'FAIL: below threshold=' + str(TRUTHFULNESS_THRESHOLD)}), "
            f"grounded={grounded_count}, synthetic={synthetic_count}, window={window_n}"
        )

        report = LearningTruthfulnessReport(
            ts_ns=ts_ns,
            window_n=window_n,
            external_ratio=external_ratio,
            synthetic_count=synthetic_count,
            grounded_count=grounded_count,
            passed=passed,
            severity=severity,
            detail=detail,
        )

        if not passed:
            append_event(
                "GOVERNANCE",
                "COGOV_LEARNING_TRUTHFULNESS",
                "cognitive_governance.learning_truthfulness",
                {
                    "signal_id": signal_id,
                    "source": source,
                    "mode": mode,
                    "grounded": grounded,
                    "external_ratio": external_ratio,
                    "grounded_count": grounded_count,
                    "synthetic_count": synthetic_count,
                    "window_n": window_n,
                    "passed": passed,
                    "severity": severity.value,
                    "violations": [v.value for v in violations],
                    "detail": detail,
                },
            )

        return report

    def get_external_ratio(self) -> float:
        """Return the current rolling external-signal ratio."""
        with self._lock:
            n = len(self._window)
            if n == 0:
                return 1.0
            return sum(1 for v in self._window if v) / n

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_grounded(external_anchors: list[str], mode: str) -> bool:
        """
        Determine whether a learning signal is externally grounded.

        A signal is grounded if:
          1. It has at least one external anchor reference, AND
          2. It is not in paper/simulation mode (paper fills are not real)

        Within GROUNDING_MAX_HOPS we trust the caller to have traced
        the anchor chain correctly. The HallucinationGuard handles
        deep structural loop detection separately.
        """
        if mode in ("paper", "simulation", "backtest"):
            return False
        # At least one non-empty anchor within the hop budget
        valid_anchors = [a for a in external_anchors if a and a.strip()]
        return len(valid_anchors) > 0


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: LearningTruthfulnessValidator | None = None
_lock = threading.Lock()


def get_learning_truthfulness_validator() -> LearningTruthfulnessValidator:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = LearningTruthfulnessValidator()
    return _instance


__all__ = ["LearningTruthfulnessValidator", "get_learning_truthfulness_validator"]
