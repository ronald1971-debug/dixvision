"""tests/test_neuromorphic.py
DIX VISION v42.2 — Neuromorphic Hazard Detector Tests

Tests for system_engine/hazard_sensors/neuromorphic_detector.py (HAZ-15).
Verifies spike-pattern detection, one-shot event emission, and
arming/disarming behaviour.

The detector requires BOTH burst density AND pairwise correlation to exceed
their thresholds simultaneously before firing.
"""

from __future__ import annotations

import pytest
from system_engine.hazard_sensors.neuromorphic_detector import NeuromorphicDetector


def _fill_high(detector: NeuromorphicDetector, n: int) -> None:
    """Fill detector window with clearly above-threshold values."""
    for _ in range(n):
        # high burst density: 1000 orders per 1 ns  (>> spike_threshold)
        detector.record_order_burst(n_orders=1000, interval_ns=1)
        # high correlation (>> correlation_threshold)
        detector.record_correlation(0.95)


def _fill_low(detector: NeuromorphicDetector, n: int) -> None:
    """Fill detector window with clearly below-threshold values."""
    for _ in range(n):
        # low burst density: 1 order per 10 seconds
        detector.record_order_burst(n_orders=1, interval_ns=10_000_000_000)
        # low correlation
        detector.record_correlation(0.05)


class TestNeuromorphicDetector:
    """HAZ-15 neuromorphic spike-pattern hazard detector."""

    def test_no_events_when_not_enough_data(self):
        detector = NeuromorphicDetector(spike_threshold=0.01, spike_window=10,
                                         correlation_threshold=0.5)
        events = detector.observe(ts_ns=1_000_000_000)
        assert events == ()

    def test_detects_spike_above_threshold(self):
        detector = NeuromorphicDetector(spike_threshold=0.01, spike_window=5,
                                         correlation_threshold=0.5)
        _fill_high(detector, 5)
        events = detector.observe(ts_ns=16_000_000)
        assert len(events) >= 1
        assert events[0].code == "HAZ-15"

    def test_one_shot_no_duplicate_events(self):
        """Latch fires exactly once; subsequent observe() returns empty."""
        detector = NeuromorphicDetector(spike_threshold=0.01, spike_window=5,
                                         correlation_threshold=0.5)
        _fill_high(detector, 5)
        events1 = detector.observe(ts_ns=16_000_000)
        events2 = detector.observe(ts_ns=17_000_000)
        assert len(events1) >= 1
        assert len(events2) == 0

    def test_reset_allows_new_detection(self):
        """After reset, the detector can fire again."""
        detector = NeuromorphicDetector(spike_threshold=0.01, spike_window=5,
                                         correlation_threshold=0.5)
        _fill_high(detector, 5)
        events1 = detector.observe(ts_ns=16_000_000)
        assert len(events1) >= 1

        detector.reset()

        _fill_high(detector, 5)
        events2 = detector.observe(ts_ns=36_000_000)
        assert len(events2) >= 1

    def test_no_false_positive_for_normal_data(self):
        """Normal data should not trigger hazard events."""
        detector = NeuromorphicDetector(spike_threshold=1000.0, spike_window=5,
                                         correlation_threshold=0.99)
        _fill_low(detector, 5)
        events = detector.observe(ts_ns=20_000_000)
        assert events == ()

    def test_both_thresholds_required(self):
        """High burst alone (without high correlation) should not fire."""
        detector = NeuromorphicDetector(spike_threshold=0.01, spike_window=5,
                                         correlation_threshold=0.9)
        for _ in range(5):
            detector.record_order_burst(n_orders=1000, interval_ns=1)  # high
            detector.record_correlation(0.1)                            # low
        events = detector.observe(ts_ns=10_000_000)
        assert events == ()

    def test_critical_severity_when_both_exceed_50_pct(self):
        """Severity escalates to CRITICAL when both metrics are 50% above threshold."""
        from core.contracts.events import HazardSeverity
        detector = NeuromorphicDetector(spike_threshold=1.0, spike_window=5,
                                         correlation_threshold=0.5)
        for _ in range(5):
            # density = 10000 / 1 = 10000, threshold = 1.0 → ratio = 10000 >> 1.5
            detector.record_order_burst(n_orders=10000, interval_ns=1)
            # correlation = 0.95, threshold = 0.5 → ratio = 1.9 >> 1.5
            detector.record_correlation(0.95)
        events = detector.observe(ts_ns=1_000_000)
        assert len(events) == 1
        assert events[0].severity == HazardSeverity.CRITICAL

    def test_reset_clears_armed_state(self):
        """reset() should clear the armed latch so the detector is unloaded."""
        detector = NeuromorphicDetector(spike_threshold=0.01, spike_window=5,
                                         correlation_threshold=0.5)
        _fill_high(detector, 5)
        detector.observe(ts_ns=1_000_000)   # arms latch
        detector.reset()
        # After reset, window is empty so observe returns ()
        events = detector.observe(ts_ns=2_000_000)
        assert events == ()
