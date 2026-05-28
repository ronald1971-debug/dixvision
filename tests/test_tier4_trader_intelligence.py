"""Tests for Tier 4.4 — Sensory-S1.D trader intelligence pipeline."""

from sensory.trader_intelligence.discovery import (
    DiscoveredTrader,
    DiscoveryPlatform,
    TraderDiscoveryEngine,
    TraderTier,
)
from sensory.trader_intelligence.monitor import (
    ExtractedSignal,
    MonitoringSchedule,
    SignalType,
    TraderMonitor,
)
from sensory.trader_intelligence.pipeline import (
    PipelineStage,
    TraderIntelligencePipeline,
)
from sensory.trader_intelligence.scorer import (
    CallOutcome,
    TraderScorer,
)


def test_discovery_add_trader():
    engine = TraderDiscoveryEngine()
    trader = DiscoveredTrader(
        platform_id="x_12345",
        platform=DiscoveryPlatform.X_TWITTER,
        display_name="CryptoWhale",
        follower_count=50000,
        post_frequency=3.0,
        focus_assets=("BTC", "ETH", "SOL"),
        estimated_tier=TraderTier.WHALE,
        first_seen_ts_ns=1000,
        credibility_signals=10,
    )
    assert engine.add_discovered(trader)
    assert engine.total_discovered == 1
    # Duplicate rejected
    assert not engine.add_discovered(trader)
    assert engine.total_discovered == 1


def test_discovery_noise_filtered():
    engine = TraderDiscoveryEngine()
    noise = DiscoveredTrader(
        platform_id="x_spam",
        platform=DiscoveryPlatform.X_TWITTER,
        display_name="SpamBot",
        follower_count=100,
        post_frequency=50.0,
        focus_assets=("SCAM",),
        estimated_tier=TraderTier.NOISE,
        first_seen_ts_ns=1000,
        credibility_signals=0,
    )
    assert not engine.add_discovered(noise)


def test_monitor_schedules():
    monitor = TraderMonitor()
    schedule = MonitoringSchedule(
        trader_id="trader_1",
        check_interval_ns=300_000,
        last_check_ts_ns=1000,
        priority=1,
        active=True,
    )
    monitor.add_schedule(schedule)
    assert monitor.active_schedules == 1

    # Not due yet
    due = monitor.get_due_checks(current_ts_ns=100_000)
    assert len(due) == 0

    # Due now
    due = monitor.get_due_checks(current_ts_ns=400_000)
    assert len(due) == 1
    assert due[0] == "trader_1"


def test_monitor_signals():
    monitor = TraderMonitor()
    signal = ExtractedSignal(
        trader_id="trader_1",
        signal_type=SignalType.POSITION_OPEN,
        symbol="BTC",
        side="long",
        confidence=0.8,
        price_level=50000.0,
        timeframe="swing",
        source_url="https://x.com/trader/status/123",
        raw_text="Going long BTC here",
        ts_ns=1000,
    )
    monitor.ingest_signal(signal)
    assert monitor.total_signals == 1

    results = monitor.get_signals(trader_id="trader_1")
    assert len(results) == 1
    assert results[0].symbol == "BTC"


def test_scorer_compute():
    scorer = TraderScorer(min_calls_for_score=3)

    # Record 5 outcomes
    for i in range(5):
        scorer.record_outcome(
            CallOutcome(
                signal_id=f"sig_{i}",
                trader_id="trader_1",
                symbol="BTC",
                side="long",
                entry_price=50000.0,
                target_price=55000.0,
                actual_price_at_target_time=52000.0 + i * 1000,
                hit_target=i >= 2,
                max_adverse=2000.0,
                time_to_target_ns=86400,
                ts_ns=i * 1000,
            )
        )

    score = scorer.compute_score("trader_1", ts_ns=10000)
    assert score is not None
    assert score.total_calls == 5
    assert score.winning_calls == 3
    assert 0.0 <= score.overall_score <= 1.0
    assert score.win_rate == 0.6


def test_scorer_insufficient_calls():
    scorer = TraderScorer(min_calls_for_score=5)
    scorer.record_outcome(
        CallOutcome(
            signal_id="sig_1",
            trader_id="trader_2",
            symbol="ETH",
            side="long",
            entry_price=3000.0,
            target_price=3500.0,
            actual_price_at_target_time=3200.0,
            hit_target=False,
            max_adverse=500.0,
            time_to_target_ns=86400,
            ts_ns=1000,
        )
    )
    assert scorer.compute_score("trader_2") is None


def test_pipeline_lifecycle():
    pipeline = TraderIntelligencePipeline()
    assert pipeline.stage == PipelineStage.IDLE
    assert pipeline.tracked_count == 0

    # Add traders
    assert pipeline.add_trader("trader_1")
    assert pipeline.add_trader("trader_2")
    assert pipeline.tracked_count == 2

    # Run cycle
    stats = pipeline.run_cycle(ts_ns=1000)
    assert stats.total_runs == 1
    assert pipeline.stage == PipelineStage.IDLE

    # Remove trader
    pipeline.remove_trader("trader_1")
    assert pipeline.tracked_count == 1
