"""tests/test_latency.py
DIX VISION v42.2 — Latency Tests

Tests for execution and market-data latency tracking:
- LatencyTracker (execution_engine/market_data/latency_tracker.py)
- LatencyModel (simulation/latency_model.py)
- LatencyImpact analysis (learning_engine/performance_analysis/latency_impact.py)
"""

from __future__ import annotations

import pytest


class TestLatencyTracker:
    def test_empty_tracker_returns_zero_stats(self):
        from execution_engine.market_data.latency_tracker import LatencyTracker
        tracker = LatencyTracker(window=100)
        stats = tracker.stats("binance", ts_ns=1_000_000_000)
        assert stats.sample_count == 0
        assert stats.mean_ns == 0.0

    def test_records_and_returns_stats(self):
        from execution_engine.market_data.latency_tracker import LatencyTracker
        tracker = LatencyTracker(window=100)
        ts = 1_000_000_000
        # Record 5 latency samples (100ms each)
        for i in range(5):
            tracker.record(
                source="binance",
                symbol="BTC/USDT",
                exchange_ts_ns=ts + i * 1_000_000_000,
                processing_ts_ns=ts + i * 1_000_000_000 + 100_000_000,  # +100ms
                ts_ns=ts + i * 1_000_000_000,
            )
        stats = tracker.stats("binance", ts_ns=ts)
        assert stats.sample_count == 5
        assert abs(stats.mean_ns - 100_000_000) < 1  # 100ms in ns

    def test_bounded_window_evicts_old_samples(self):
        from execution_engine.market_data.latency_tracker import LatencyTracker
        tracker = LatencyTracker(window=5)
        ts = 0
        for i in range(10):
            tracker.record("venue", "SYM", ts + i, ts + i + 1000, ts + i)
        stats = tracker.stats("venue", ts_ns=ts)
        assert stats.sample_count <= 5

    def test_percentile_monotonic(self):
        from execution_engine.market_data.latency_tracker import LatencyTracker
        tracker = LatencyTracker(window=1000)
        ts = 0
        for i in range(100):
            tracker.record("ex", "S", ts, ts + i * 1_000_000, ts)
        stats = tracker.stats("ex", ts_ns=ts)
        assert stats.p50_ns <= stats.p95_ns <= stats.p99_ns


class TestSimulationLatencyModel:
    def test_paper_trading_latency_near_zero(self):
        from simulation.latency_model import LatencyModel, LatencyConfig, VenueLatencyProfile
        model = LatencyModel(seed=42)
        model.register_venue(LatencyConfig(venue="paper", profile=VenueLatencyProfile.PAPER))
        draw = model.sample("paper", submission_ts_ns=1_000_000_000)
        assert draw.latency_ms < 10.0  # paper is near-instant

    def test_deterministic_sample_same_seed_same_result(self):
        from simulation.latency_model import LatencyModel
        model = LatencyModel(seed=42)
        d1 = model.deterministic_sample("binance", 1_000_000_000, sequence=1)
        d2 = model.deterministic_sample("binance", 1_000_000_000, sequence=1)
        assert d1.latency_ms == d2.latency_ms

    def test_fill_ts_after_submission(self):
        from simulation.latency_model import LatencyModel
        model = LatencyModel(seed=99)
        sub_ts = 5_000_000_000_000_000
        draw = model.sample("binance", submission_ts_ns=sub_ts)
        assert draw.fill_ts_ns >= sub_ts


class TestLatencyImpactAnalysis:
    def test_zero_impact_when_prices_equal(self):
        from learning_engine.performance_analysis.latency_impact import compute_latency_impact
        record = compute_latency_impact(
            strategy_id="STR-001",
            venue="binance",
            symbol="BTC/USDT",
            side="BUY",
            signal_ts_ns=1000,
            fill_ts_ns=101_000_000,
            signal_price=50_000.0,
            fill_price=50_000.0,
            qty=1.0,
        )
        assert record.impact_bps == 0.0
        assert record.impact_usd == 0.0

    def test_adverse_impact_on_buy_fill_higher(self):
        from learning_engine.performance_analysis.latency_impact import compute_latency_impact
        record = compute_latency_impact(
            strategy_id="STR-001",
            venue="binance",
            symbol="BTC/USDT",
            side="BUY",
            signal_ts_ns=1000,
            fill_ts_ns=100_000_000,
            signal_price=50_000.0,
            fill_price=50_250.0,  # slipped higher
            qty=1.0,
        )
        assert record.impact_bps > 0   # adverse (paid more)
        assert record.impact_usd > 0

    def test_latency_ns_computed_correctly(self):
        from learning_engine.performance_analysis.latency_impact import compute_latency_impact
        record = compute_latency_impact(
            strategy_id="STR-001",
            venue="binance",
            symbol="ETH/USDT",
            side="SELL",
            signal_ts_ns=0,
            fill_ts_ns=200_000_000,  # 200ms
            signal_price=3000.0,
            fill_price=3000.0,
            qty=10.0,
        )
        assert record.latency_ns == 200_000_000
