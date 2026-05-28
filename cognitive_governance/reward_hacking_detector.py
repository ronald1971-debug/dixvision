"""
cognitive_governance/reward_hacking_detector.py
DIX VISION v42.2 — Reward Hacking Detector

Detects when the learning system optimizes the reward signal itself
rather than the true underlying objective.

The fundamental diagnostic: if the reward INCREASES while the true
objective metrics DEGRADE, the system is hacking its reward function.

Measured as the Pearson correlation between:
  - reward_trend  (rolling slope of the reward signal per strategy)
  - objective_trend (rolling slope of calibration accuracy / epistemic drift)

Healthy learning: reward_trend and objective_trend are positively
correlated (correlation > HEALTHY_CORRELATION).

Reward hacking: correlation < HACKING_THRESHOLD (reward improving
while objective degrades, or vice versa).

Additionally detects SUSPICIOUSLY_PERFECT_SCORES: strategies whose
rolling win-rate standard deviation is < PERFECTION_SIGMA. Real
markets are noisy; unnaturally smooth reward curves indicate the
system found a way to game the simulator.
"""

from __future__ import annotations

import math
import threading
from collections import deque

from core.contracts.cognitive_governance import (
    CognitiveSeverity,
    CognitiveViolationKind,
    RewardHackingReport,
)
from state.ledger.event_store import append_event

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_SIZE = 100
HEALTHY_CORRELATION = 0.40
HACKING_THRESHOLD = 0.10
PERFECTION_SIGMA = 0.02


class RewardHackingDetector:
    """
    Detects reward-function gaming by correlating reward trends with
    true objective trends per strategy.
    """

    def __init__(self) -> None:
        # strategy_id → deque of (reward: float, objective: float)
        self._samples: dict[str, deque[tuple[float, float]]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_reward_sample(
        self,
        strategy_id: str,
        reward: float,
        objective_metric: float,
        ts_ns: int,
    ) -> RewardHackingReport:
        """
        Record a (reward, objective_metric) pair for a strategy.

        objective_metric: the true underlying objective (e.g., calibration
        accuracy, epistemic drift inverse, Sharpe). This should be the
        quantity we actually care about, not the reward proxy.

        Returns RewardHackingReport. Callers should escalate hacking_detected
        reports to Governance for strategy review.
        """
        with self._lock:
            if strategy_id not in self._samples:
                self._samples[strategy_id] = deque(maxlen=WINDOW_SIZE)
            self._samples[strategy_id].append((reward, objective_metric))
            samples = list(self._samples[strategy_id])

        n = len(samples)

        if n < 10:
            # Not enough data for meaningful trend/correlation analysis
            return RewardHackingReport(
                ts_ns=ts_ns,
                strategy_id=strategy_id,
                reward_trend=0.0,
                objective_trend=0.0,
                correlation=1.0,  # assume healthy until proven otherwise
                hacking_detected=False,
                severity=CognitiveSeverity.INFO,
                detail=f"insufficient samples (n={n}, need >= 10)",
            )

        rewards = [r for r, _ in samples]
        objectives = [o for _, o in samples]

        reward_trend = self._linear_trend(rewards)
        objective_trend = self._linear_trend(objectives)
        correlation = self._compute_pearson(rewards, objectives)
        perfect_score = self._detect_perfect_score(strategy_id)

        # Detect hacking conditions
        hacking_detected = False
        violations: list[CognitiveViolationKind] = []
        detail_parts: list[str] = []

        if correlation < HACKING_THRESHOLD:
            hacking_detected = True
            violations.append(CognitiveViolationKind.REWARD_HACKING)
            detail_parts.append(
                f"reward-objective correlation={correlation:.4f} < "
                f"HACKING_THRESHOLD={HACKING_THRESHOLD}; "
                f"reward_trend={reward_trend:+.4f}, objective_trend={objective_trend:+.4f}"
            )

        if perfect_score:
            hacking_detected = True
            violations.append(CognitiveViolationKind.SELF_REFERENTIAL_REWARD)
            detail_parts.append(
                f"reward std_dev < PERFECTION_SIGMA={PERFECTION_SIGMA}; "
                "unnaturally smooth reward curve — possible simulator gaming"
            )

        # Severity
        if hacking_detected:
            if correlation < HACKING_THRESHOLD * 0.5:
                severity = CognitiveSeverity.CRITICAL
            else:
                severity = CognitiveSeverity.HIGH
        elif correlation < HEALTHY_CORRELATION:
            severity = CognitiveSeverity.WARNING
        else:
            severity = CognitiveSeverity.INFO

        detail = "; ".join(detail_parts) if detail_parts else (
            f"correlation={correlation:.4f}, reward_trend={reward_trend:+.4f}, "
            f"objective_trend={objective_trend:+.4f}, OK"
        )

        report = RewardHackingReport(
            ts_ns=ts_ns,
            strategy_id=strategy_id,
            reward_trend=reward_trend,
            objective_trend=objective_trend,
            correlation=correlation,
            hacking_detected=hacking_detected,
            severity=severity,
            detail=detail,
        )

        if hacking_detected:
            append_event(
                "GOVERNANCE",
                "COGOV_REWARD_HACKING",
                "cognitive_governance.reward_hacking_detector",
                {
                    "strategy_id": strategy_id,
                    "reward_trend": reward_trend,
                    "objective_trend": objective_trend,
                    "correlation": correlation,
                    "hacking_detected": hacking_detected,
                    "perfect_score": perfect_score,
                    "n_samples": n,
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
    def _compute_pearson(xs: list[float], ys: list[float]) -> float:
        """
        Compute Pearson correlation coefficient between two equal-length lists.

        Returns 0.0 if variance is zero in either series (constant signal).
        """
        n = len(xs)
        if n < 2 or len(ys) != n:
            return 0.0

        mean_x = sum(xs) / n
        mean_y = sum(ys) / n

        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        var_x = sum((x - mean_x) ** 2 for x in xs)
        var_y = sum((y - mean_y) ** 2 for y in ys)

        denom = math.sqrt(var_x * var_y)
        if denom == 0.0:
            return 0.0

        r = num / denom
        return max(-1.0, min(1.0, r))

    def _detect_perfect_score(self, strategy_id: str) -> bool:
        """
        Detect suspiciously perfect reward curves.

        Computes the standard deviation of the reward series. Values
        below PERFECTION_SIGMA indicate unnaturally smooth rewards.

        Assumes _lock is NOT held (reads from already-snapped samples).
        """
        with self._lock:
            samples = list(self._samples.get(strategy_id, deque()))

        rewards = [r for r, _ in samples]
        n = len(rewards)
        if n < 10:
            return False

        mean_r = sum(rewards) / n
        variance = sum((r - mean_r) ** 2 for r in rewards) / n
        std_r = math.sqrt(variance)

        return std_r < PERFECTION_SIGMA

    @staticmethod
    def _linear_trend(values: list[float]) -> float:
        """
        Compute the slope of a linear regression through the values.

        Returns the slope (positive = upward trend, negative = downward).
        Uses index as the x-axis (0, 1, 2, ..., n-1).
        """
        n = len(values)
        if n < 2:
            return 0.0

        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n

        num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denom = sum((i - x_mean) ** 2 for i in range(n))

        if denom == 0.0:
            return 0.0

        return num / denom


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: RewardHackingDetector | None = None
_lock = threading.Lock()


def get_reward_hacking_detector() -> RewardHackingDetector:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = RewardHackingDetector()
    return _instance


__all__ = ["RewardHackingDetector", "get_reward_hacking_detector"]
