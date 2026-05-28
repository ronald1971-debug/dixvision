"""HAZ-15 — neuromorphic (spike-pattern) anomaly sensor.

Detects sudden bursts of correlated orders that suggest coordinated
manipulation or a feedback loop in order flow. Two concurrent conditions
must both be met to fire:

* **burst density**: ``n_orders / interval_ns`` exceeds ``_spike_threshold``
  over the rolling ``_spike_window``.
* **pairwise correlation**: recorded correlation values exceed
  ``_correlation_threshold`` over the same window.

Severity is HIGH normally; CRITICAL when both thresholds are exceeded by
50 % or more simultaneously.

One-shot armed pattern (same as latency_spike.py): the event is emitted
once when the condition first becomes true; subsequent ``observe`` calls
return ``()`` while armed. The sensor resets to unarmed only when *both*
signals drop back below their respective thresholds.
"""

from __future__ import annotations

from collections import deque

from core.contracts.events import HazardEvent, HazardSeverity


class NeuromorphicDetector:
    """HAZ-15. Detects neuromorphic spike-pattern anomalies in order flow."""

    name: str = "neuromorphic_detector"
    code: str = "HAZ-15"
    spec_id: str = "HAZ-15"
    source: str = "system_engine.hazard_sensors.neuromorphic_detector"

    __slots__ = (
        "_spike_window",
        "_correlation_window",
        "_spike_threshold",
        "_correlation_threshold",
        "_armed",
        "_burst_samples",
        "_corr_samples",
    )

    def __init__(
        self,
        spike_window: int = 16,
        spike_threshold: float = 0.75,
        correlation_threshold: float = 0.8,
    ) -> None:
        if spike_window < 1:
            raise ValueError("spike_window must be >= 1")
        if spike_threshold <= 0.0:
            raise ValueError("spike_threshold must be positive")
        if not 0.0 < correlation_threshold <= 1.0:
            raise ValueError("correlation_threshold must be in (0, 1]")
        self._spike_window = spike_window
        self._correlation_window = spike_window  # same window size for both signals
        self._spike_threshold = spike_threshold
        self._correlation_threshold = correlation_threshold
        self._armed = False
        self._burst_samples: deque[float] = deque(maxlen=spike_window)
        self._corr_samples: deque[float] = deque(maxlen=spike_window)

    def record_order_burst(self, n_orders: int, interval_ns: int) -> None:
        """Record a burst density observation: n_orders / interval_ns.

        Parameters
        ----------
        n_orders:
            Number of orders seen in the interval.
        interval_ns:
            Length of the observation interval in nanoseconds. Must be > 0.
        """
        if interval_ns <= 0:
            raise ValueError("interval_ns must be positive")
        density = n_orders / interval_ns
        self._burst_samples.append(density)

    def record_correlation(self, corr: float) -> None:
        """Record a pairwise order correlation observation.

        Parameters
        ----------
        corr:
            Pairwise correlation coefficient, expected in ``[0.0, 1.0]``.
        """
        self._corr_samples.append(corr)

    def observe(self, ts_ns: int) -> tuple[HazardEvent, ...]:
        """Evaluate current window; fire HAZ-15 on first threshold crossing.

        Returns a single-element tuple on the first tick where both spike
        density and correlation exceed their thresholds simultaneously.
        Returns ``()`` while the armed latch is held, or while insufficient
        samples are available.

        The latch resets when *both* signals fall back below their thresholds.
        """
        if len(self._burst_samples) < self._spike_window:
            return ()
        if len(self._corr_samples) < self._correlation_window:
            return ()

        mean_density = sum(self._burst_samples) / len(self._burst_samples)
        mean_corr = sum(self._corr_samples) / len(self._corr_samples)

        spike_triggered = mean_density >= self._spike_threshold
        corr_triggered = mean_corr >= self._correlation_threshold

        if not (spike_triggered and corr_triggered):
            # Both must be below threshold to disarm.
            if not spike_triggered and not corr_triggered:
                self._armed = False
            return ()

        if self._armed:
            return ()

        self._armed = True

        # Determine severity: CRITICAL if both exceed thresholds by >= 50 %.
        density_excess = mean_density / self._spike_threshold
        corr_excess = mean_corr / self._correlation_threshold
        if density_excess >= 1.5 and corr_excess >= 1.5:
            severity = HazardSeverity.CRITICAL
        else:
            severity = HazardSeverity.HIGH

        return (
            HazardEvent(
                ts_ns=ts_ns,
                code=self.code,
                severity=severity,
                source=self.source,
                detail=(
                    f"neuromorphic spike detected: "
                    f"density={mean_density:.4g} >= {self._spike_threshold:.4g}, "
                    f"correlation={mean_corr:.4f} >= {self._correlation_threshold:.4f}"
                ),
                meta={
                    "mean_density": f"{mean_density:.6g}",
                    "spike_threshold": f"{self._spike_threshold:.6g}",
                    "mean_correlation": f"{mean_corr:.6f}",
                    "correlation_threshold": f"{self._correlation_threshold:.6f}",
                    "window": str(self._spike_window),
                    "severity": severity.value,
                },
                produced_by_engine="system_engine",
            ),
        )


__all__ = ["NeuromorphicDetector"]
