"""tests/test_neuromorphic.py
DIX VISION v42.2 — Neuromorphic Hazard Detector Tests

Tests for system_engine/hazard_sensors/neuromorphic_detector.py (HAZ-15).
Verifies spike-pattern detection, one-shot event emission, and
arming/disarming behaviour.
"""

from __future__ import annotations

import pytest
from system_engine.hazard_sensors.neuromorphic_detector import NeuromorphicDetector


class TestNeuromorphicDetector:
    """HAZ-15 neuromorphic spike-pattern hazard detector."""

    def test_no_events_when_not_enough_data(self):
        detector = NeuromorphicDetector(spike_threshold=3.0, window=10)
        events = detector.observe(ts_ns=1_000_000_000)
        assert events == ()

    def test_detects_spike_above_threshold(self):
        detector = NeuromorphicDetector(spike_threshold=2.0, window=20)
        # Feed normal values
        for i in range(15):
            detector.feed(1.0 + i * 0.01, ts_ns=i * 1_000_000)
        # Feed spike
        detector.feed(100.0, ts_ns=15 * 1_000_000)
        events = detector.observe(ts_ns=16 * 1_000_000)
        assert len(events) >= 1
        assert any("HAZ" in e.hazard_id or "NEURO" in e.hazard_id.upper() for e in events)

    def test_one_shot_no_duplicate_events(self):
        """Same spike pattern should not produce duplicate events."""
        detector = NeuromorphicDetector(spike_threshold=2.0, window=20)
        for i in range(15):
            detector.feed(1.0, ts_ns=i * 1_000_000)
        detector.feed(100.0, ts_ns=15 * 1_000_000)

        events1 = detector.observe(ts_ns=16_000_000)
        events2 = detector.observe(ts_ns=17_000_000)

        # Second observe on same pattern should return nothing
        total = len(events1) + len(events2)
        assert total == len(events1)  # no new events on second call

    def test_reset_allows_new_detection(self):
        """After reset, the detector can fire again."""
        detector = NeuromorphicDetector(spike_threshold=2.0, window=20)
        for i in range(15):
            detector.feed(1.0, ts_ns=i * 1_000_000)
        detector.feed(100.0, ts_ns=15_000_000)
        events1 = detector.observe(ts_ns=16_000_000)

        detector.reset()

        for i in range(15):
            detector.feed(1.0, ts_ns=(20 + i) * 1_000_000)
        detector.feed(100.0, ts_ns=35_000_000)
        events2 = detector.observe(ts_ns=36_000_000)

        assert len(events2) >= 1

    def test_no_false_positive_for_normal_data(self):
        """Normal data should not trigger hazard events."""
        detector = NeuromorphicDetector(spike_threshold=5.0, window=20)
        for i in range(20):
            detector.feed(1.0 + 0.01 * (i % 5), ts_ns=i * 1_000_000)
        events = detector.observe(ts_ns=20_000_000)
        assert events == ()
