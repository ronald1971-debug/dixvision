"""ReflectionEngine — self-evaluation after every decision.

Core loop: expected_outcome vs real_outcome → mismatch → adjust beliefs.
This is what makes the system "human" — it analyzes its own decisions.

Reflection is a SLOW process (not hot-path). It runs post-decision
and feeds back into the learning loop. Pure / deterministic (INV-15).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MismatchSeverity(StrEnum):
    """How bad was the prediction vs reality gap."""

    NONE = "NONE"  # outcome matched expectation
    MINOR = "MINOR"  # small deviation (within noise)
    SIGNIFICANT = "SIGNIFICANT"  # meaningful error
    CRITICAL = "CRITICAL"  # completely wrong (e.g., predicted up, went down hard)


class MismatchType(StrEnum):
    """What dimension was the mismatch in."""

    DIRECTION = "DIRECTION"  # predicted direction wrong
    MAGNITUDE = "MAGNITUDE"  # direction right, magnitude wrong
    TIMING = "TIMING"  # direction right, but too early/late
    REGIME = "REGIME"  # wrong regime classification
    CONFIDENCE = "CONFIDENCE"  # confidence was miscalibrated
    EXECUTION = "EXECUTION"  # decision was right but execution failed


@dataclass(frozen=True, slots=True)
class DecisionExpectation:
    """What the system expected when making a decision."""

    decision_id: str
    ts_ns: int
    predicted_direction: str  # UP, DOWN, FLAT
    predicted_magnitude_bps: float
    predicted_holding_ns: int
    confidence: float  # [0, 1]
    regime_prediction: str
    strategy_id: str


@dataclass(frozen=True, slots=True)
class RealizedOutcome:
    """What actually happened."""

    decision_id: str
    ts_ns: int
    actual_direction: str
    actual_magnitude_bps: float
    actual_holding_ns: int
    actual_regime: str
    pnl_bps: float


@dataclass(frozen=True, slots=True)
class ReflectionResult:
    """Output of self-reflection on one decision."""

    decision_id: str
    mismatch_severity: MismatchSeverity
    mismatch_types: tuple[MismatchType, ...]
    confidence_error: float  # how miscalibrated was confidence
    direction_correct: bool
    magnitude_error_bps: float
    timing_error_ns: int
    belief_adjustment: dict[str, float]  # suggested belief updates
    lesson: str  # human-readable lesson learned


class ReflectionEngine:
    """Analyzes decisions post-hoc and generates belief adjustments.

    On each reflection cycle:
    1. Compare expected vs realized outcome.
    2. Classify mismatch type and severity.
    3. Compute belief adjustments (what should change).
    4. Store lesson for future pattern matching.
    """

    def __init__(self, *, severity_threshold_bps: float = 50.0) -> None:
        self._threshold_bps = severity_threshold_bps
        self._reflections: list[ReflectionResult] = []
        self._belief_drift: dict[str, float] = {}

    @property
    def reflections(self) -> list[ReflectionResult]:
        return list(self._reflections)

    @property
    def belief_drift(self) -> dict[str, float]:
        """Accumulated belief adjustments from reflection."""
        return dict(self._belief_drift)

    def reflect(
        self,
        expected: DecisionExpectation,
        realized: RealizedOutcome,
    ) -> ReflectionResult:
        """Perform one reflection cycle on a completed decision."""
        mismatches: list[MismatchType] = []

        # Direction check
        direction_correct = expected.predicted_direction == realized.actual_direction
        if not direction_correct:
            mismatches.append(MismatchType.DIRECTION)

        # Magnitude check
        magnitude_error = abs(realized.actual_magnitude_bps - expected.predicted_magnitude_bps)
        if magnitude_error > self._threshold_bps:
            mismatches.append(MismatchType.MAGNITUDE)

        # Timing check
        timing_error = abs(realized.actual_holding_ns - expected.predicted_holding_ns)
        if timing_error > expected.predicted_holding_ns * 0.5:
            mismatches.append(MismatchType.TIMING)

        # Regime check
        if expected.regime_prediction != realized.actual_regime:
            mismatches.append(MismatchType.REGIME)

        # Confidence calibration
        actual_success = 1.0 if realized.pnl_bps > 0 else 0.0
        confidence_error = abs(expected.confidence - actual_success)
        if confidence_error > 0.4:
            mismatches.append(MismatchType.CONFIDENCE)

        # Classify severity
        severity = self._classify_severity(mismatches, magnitude_error, direction_correct)

        # Generate belief adjustments
        adjustments = self._compute_adjustments(expected, realized, mismatches, confidence_error)

        # Generate lesson
        lesson = self._generate_lesson(mismatches, severity, expected, realized)

        result = ReflectionResult(
            decision_id=expected.decision_id,
            mismatch_severity=severity,
            mismatch_types=tuple(mismatches),
            confidence_error=confidence_error,
            direction_correct=direction_correct,
            magnitude_error_bps=magnitude_error,
            timing_error_ns=timing_error,
            belief_adjustment=adjustments,
            lesson=lesson,
        )

        self._reflections.append(result)
        # Accumulate belief drift
        for key, val in adjustments.items():
            self._belief_drift[key] = self._belief_drift.get(key, 0.0) + val

        return result

    def _classify_severity(
        self,
        mismatches: list[MismatchType],
        magnitude_error: float,
        direction_correct: bool,
    ) -> MismatchSeverity:
        if not mismatches:
            return MismatchSeverity.NONE
        if MismatchType.DIRECTION in mismatches and magnitude_error > self._threshold_bps * 2:
            return MismatchSeverity.CRITICAL
        if len(mismatches) >= 3 or MismatchType.DIRECTION in mismatches:
            return MismatchSeverity.SIGNIFICANT
        return MismatchSeverity.MINOR

    def _compute_adjustments(
        self,
        expected: DecisionExpectation,
        realized: RealizedOutcome,
        mismatches: list[MismatchType],
        confidence_error: float,
    ) -> dict[str, float]:
        """Compute belief adjustments based on reflection."""
        adj: dict[str, float] = {}

        if MismatchType.DIRECTION in mismatches:
            adj["direction_trust"] = -0.1
            adj[f"strategy_{expected.strategy_id}_confidence"] = -0.15

        if MismatchType.REGIME in mismatches:
            adj["regime_detection_accuracy"] = -0.05
            adj[f"regime_{expected.regime_prediction}_reliability"] = -0.1

        if MismatchType.CONFIDENCE in mismatches:
            # Overconfident → reduce; underconfident → increase
            if expected.confidence > 0.5 and realized.pnl_bps < 0:
                adj["confidence_calibration"] = -0.1
            elif expected.confidence < 0.5 and realized.pnl_bps > 0:
                adj["confidence_calibration"] = 0.05

        if MismatchType.MAGNITUDE in mismatches:
            adj["magnitude_estimation"] = -0.05

        if not mismatches:
            # Reward correct predictions
            adj[f"strategy_{expected.strategy_id}_confidence"] = 0.02
            adj["overall_calibration"] = 0.01

        return adj

    def _generate_lesson(
        self,
        mismatches: list[MismatchType],
        severity: MismatchSeverity,
        expected: DecisionExpectation,
        realized: RealizedOutcome,
    ) -> str:
        """Generate human-readable lesson."""
        if severity == MismatchSeverity.NONE:
            return f"Decision {expected.decision_id}: prediction accurate."
        parts = []
        if MismatchType.DIRECTION in mismatches:
            parts.append(
                f"predicted {expected.predicted_direction} but got {realized.actual_direction}"
            )
        if MismatchType.REGIME in mismatches:
            parts.append(f"regime was {realized.actual_regime} not {expected.regime_prediction}")
        if MismatchType.CONFIDENCE in mismatches:
            parts.append(f"confidence {expected.confidence:.0%} was miscalibrated")
        return f"Decision {expected.decision_id} ({severity}): {'; '.join(parts)}."
