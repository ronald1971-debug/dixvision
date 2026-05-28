"""core/coherence/drift_oracle.py
DIX VISION v42.2 — Regime drift detector between predicted and actual
market behaviour.

The :class:`DriftOracle` maintains a per-metric rolling window of
(predicted, actual) sample pairs and computes a z-score for each metric
on every new sample. When the z-score exceeds the configured critical
threshold the metric is flagged as ``drifting``.

Design:
* Rolling window uses a fixed-size circular buffer per metric (no
  external dependencies, no I/O).
* z-score is computed as ``(mean_delta - 0) / std_delta`` where
  ``delta = predicted - actual`` and the reference mean is 0.0 (a
  well-calibrated system has mean delta ≈ 0).
* The oracle is NOT a pure function at the class level (it holds mutable
  window state) but :meth:`record_sample` is functionally pure over its
  return value — same sequence of calls produces the same sequence of
  :class:`DriftMeasure` outputs (INV-15 for replay).

Authority constraints:
* No imports from any ``*_engine`` package.
* No imports from ``state.ledger`` writers.
* Only stdlib ``math`` and ``statistics`` imports plus
  ``core.contracts`` (none needed here).
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DriftMeasure:
    """Single-sample drift observation for one named metric.

    Fields:
        ts_ns: Nanosecond timestamp (caller-supplied, INV-15).
        metric_name: Identifier of the monitored metric.
        predicted: The value the system predicted for this metric.
        actual: The value observed in reality.
        delta: ``predicted - actual``.
        z_score: Standardised deviation of ``delta`` from zero within
            the rolling window (0.0 if fewer than 2 samples).
        drifting: True if ``abs(z_score) >= DriftOracleConfig.z_warn``.
    """

    ts_ns: int
    metric_name: str
    predicted: float
    actual: float
    delta: float
    z_score: float
    drifting: bool


@dataclass(frozen=True, slots=True)
class DriftOracleConfig:
    """Hyper-parameters for :class:`DriftOracle`.

    Fields:
        window_size: Number of (predicted, actual) samples to retain
            per metric. Older samples are discarded in FIFO order.
            Minimum 2 (z-score requires at least 2 samples to compute
            a non-zero std-dev).
        z_warn: Absolute z-score threshold above which a metric is
            flagged ``drifting=True``.
        z_critical: Absolute z-score threshold above which
            :class:`~core.coherence.meta_adaptation.MetaAdaptation`
            should escalate to a critical adaptation signal.
    """

    window_size: int = 100
    z_warn: float = 2.0
    z_critical: float = 3.5


class DriftOracle:
    """Rolling-window z-score regime drift detector.

    One :class:`DriftOracle` instance is shared by the coherence
    coordinator. It accepts (predicted, actual) samples per named metric
    and flags metrics that exhibit statistically significant drift from
    zero-delta calibration.

    Thread-safety: not thread-safe — callers must serialize access or
    use a lock at the coordinator level.
    """

    def __init__(self, config: DriftOracleConfig | None = None) -> None:
        self._config = config or DriftOracleConfig()
        # Per-metric rolling window of delta values
        self._windows: dict[str, deque[float]] = {}

    @property
    def config(self) -> DriftOracleConfig:
        return self._config

    # ------------------------------------------------------------------
    # Sample ingestion
    # ------------------------------------------------------------------

    def record_sample(
        self,
        metric_name: str,
        predicted: float,
        actual: float,
        ts_ns: int,
    ) -> DriftMeasure:
        """Record one (predicted, actual) pair and return a DriftMeasure.

        The rolling window is updated in-place; older samples beyond
        ``config.window_size`` are discarded.

        Args:
            metric_name: Identifier of the metric being tracked.
            predicted: Model-predicted value.
            actual: Observed (real) value.
            ts_ns: Timestamp in nanoseconds (caller-provided — INV-15).

        Returns:
            A :class:`DriftMeasure` summarising the current state of
            the metric after incorporating this sample.
        """
        delta = predicted - actual

        window = self._windows.setdefault(
            metric_name,
            deque(maxlen=self._config.window_size),
        )
        window.append(delta)

        z_score = self._compute_z(window)
        drifting = abs(z_score) >= self._config.z_warn

        return DriftMeasure(
            ts_ns=ts_ns,
            metric_name=metric_name,
            predicted=predicted,
            actual=actual,
            delta=delta,
            z_score=z_score,
            drifting=drifting,
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_drift_summary(self) -> dict[str, float]:
        """Return the current z-score per tracked metric.

        Returns a freshly-constructed dict; mutations do not affect
        the oracle's internal state.

        Returns:
            ``{metric_name: z_score}`` for every metric with at least
            one sample. Metrics with fewer than 2 samples will have
            z-score 0.0.
        """
        return {
            name: self._compute_z(window)
            for name, window in self._windows.items()
        }

    def tracked_metrics(self) -> tuple[str, ...]:
        """Return a sorted tuple of all currently tracked metric names."""
        return tuple(sorted(self._windows))

    def reset_metric(self, metric_name: str) -> None:
        """Discard all samples for ``metric_name`` (e.g. after a mode reset)."""
        self._windows.pop(metric_name, None)

    def reset_all(self) -> None:
        """Discard all samples for all metrics."""
        self._windows.clear()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_z(window: deque[float]) -> float:  # type: ignore[type-arg]
        """Compute the z-score of the most-recent delta within the window.

        The reference distribution is the rolling window of deltas. The
        z-score measures how many standard deviations the most-recent
        delta is from the window mean. If the window has fewer than 2
        samples a std-dev cannot be computed and 0.0 is returned.

        Pure given the window contents (INV-15).
        """
        n = len(window)
        if n < 2:
            return 0.0
        samples = list(window)
        mean = statistics.mean(samples)
        # Use population stdev when the entire window is treated as the
        # reference distribution (not a sample from a larger population).
        stdev = statistics.pstdev(samples)
        if stdev == 0.0 or not math.isfinite(stdev):
            return 0.0
        # z-score of the most recently added delta
        latest = samples[-1]
        return (latest - mean) / stdev


__all__ = [
    "DriftMeasure",
    "DriftOracle",
    "DriftOracleConfig",
]
