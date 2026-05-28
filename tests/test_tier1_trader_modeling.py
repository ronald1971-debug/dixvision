"""Tests for Tier 1 trader modeling modules."""

from intelligence_engine.trader_modeling.content_parser import (
    ContentParser,
    ContentType,
)
from intelligence_engine.trader_modeling.credibility_filter import (
    CredibilityFilter,
    CredibilityTier,
)
from intelligence_engine.trader_modeling.imitation import (
    ImitationAction,
    ImitationEngine,
)
from intelligence_engine.trader_modeling.meta_controller_bridge import (
    MetaControllerBridge,
)
from intelligence_engine.trader_modeling.narrative_alignment import (
    NarrativeAlignmentEngine,
    NarrativeSignal,
)
from intelligence_engine.trader_modeling.performance_tracker import (
    PerformanceTracker,
)
from intelligence_engine.trader_modeling.strategy_similarity_engine import (
    StrategySimilarityEngine,
)
from intelligence_engine.trader_modeling.trader_behavior_tracker import (
    TraderBehaviorTracker,
)
from intelligence_engine.trader_modeling.trader_clustering import (
    TraderClustering,
)
from intelligence_engine.trader_modeling.trader_pattern_extractor import (
    PatternType,
    TraderPatternExtractor,
)
from intelligence_engine.trader_modeling.trader_profile_engine import (
    ProfileStatus,
    TraderProfileEngine,
)
from intelligence_engine.trader_modeling.trader_reliability_engine import (
    TraderReliabilityEngine,
)


def test_credibility_filter_legendary():
    f = CredibilityFilter()
    result = f.assess(
        trader_id="soros",
        track_record_years=40.0,
        verified_returns=True,
        onchain_proof=True,
        published_results=True,
        peer_citations=50,
    )
    assert result.tier == CredibilityTier.LEGENDARY
    assert result.score >= 0.7
    assert result.pass_filter is True


def test_credibility_filter_reject_fraud():
    f = CredibilityFilter()
    result = f.assess(trader_id="scammer", known_fraud=True)
    assert result.tier == CredibilityTier.REJECTED
    assert result.pass_filter is False


def test_content_parser_extracts():
    p = ContentParser()
    result = p.parse(
        content_id="c1",
        content_type=ContentType.TEXT_POST,
        trader_id="t1",
        raw_text="BTC breakout confirmed, stop loss at 60k, bullish 4h",
        ts_ns=1000,
    )
    assert "breakout" in result.extracted_setups
    assert "stop loss" in result.extracted_rules
    assert "BTC" in result.mentioned_instruments
    assert "4H" in result.mentioned_timeframes
    assert result.sentiment > 0  # bullish


def test_profile_engine_crud():
    engine = TraderProfileEngine()
    p = engine.create_profile(
        canonical_id="ptj",
        display_name="Paul Tudor Jones",
        archetype="macro",
    )
    assert p.status == ProfileStatus.ACTIVE
    assert engine.profile_count == 1

    engine.update_observation(canonical_id="ptj", atom_ids=["a1", "a2"], ts_ns=100)
    p2 = engine.get_profile("ptj")
    assert p2 is not None
    assert p2.total_observations == 1
    assert len(p2.atom_ids) == 2


def test_behavior_tracker():
    tracker = TraderBehaviorTracker(window_size=50)
    for i in range(20):
        tracker.record_decision(
            trader_id="t1",
            ts_ns=i * 1000,
            regime="TRENDING_BULL",
            decision_type="entry",
            outcome=1.0 if i % 3 != 0 else -1.0,
        )
    snap = tracker.snapshot("t1", ts_ns=20000)
    assert snap.recent_decisions == 20
    assert snap.consistency_score > 0.5


def test_pattern_extractor():
    extractor = TraderPatternExtractor(min_frequency=2, min_success=0.4)
    for i in range(5):
        extractor.observe(
            trader_id="t1",
            action_type="entry_buy",
            regime="TRENDING",
            outcome=0.5,
            conditions={"rsi": 30.0},
            ts_ns=i * 1000,
        )
    patterns = extractor.extract("t1")
    assert len(patterns) >= 1
    assert patterns[0].pattern_type == PatternType.ENTRY


def test_reliability_engine():
    engine = TraderReliabilityEngine(decay_halflife_days=30)
    for i in range(10):
        engine.record_outcome(trader_id="t1", correct=i < 8, regime="VOLATILE", ts_ns=i)
    score = engine.reliability_score("t1")
    assert score > 0.6


def test_clustering():
    cluster = TraderClustering(target_clusters=5)
    cid1 = cluster.assign(trader_id="t1", embedding=(1.0, 0.0, 0.0))
    cid2 = cluster.assign(trader_id="t2", embedding=(0.9, 0.1, 0.0))
    # Similar traders should be in same cluster
    assert cid1 == cid2


def test_similarity_engine():
    engine = StrategySimilarityEngine(dedup_threshold=0.9)
    engine.register_embedding("a1", (1.0, 0.0, 0.5))
    engine.register_embedding("a2", (1.0, 0.01, 0.5))
    engine.register_embedding("a3", (0.0, 1.0, 0.0))
    result = engine.compare("a1", "a2")
    assert result.cosine_similarity > 0.9
    result2 = engine.compare("a1", "a3")
    assert result2.cosine_similarity < 0.5


def test_narrative_alignment():
    engine = NarrativeAlignmentEngine(decay_window_ns=100000)
    for i in range(5):
        engine.ingest_signal(
            NarrativeSignal(
                narrative_id=f"n{i}",
                source=f"trader_{i}",
                theme="risk_off",
                conviction=0.8,
                ts_ns=1000 + i,
            )
        )
    alignment = engine.measure_alignment(theme="risk_off", ts_ns=2000)
    assert alignment.alignment_score > 0.5
    assert len(alignment.aligned_traders) >= 3


def test_imitation_engine():
    engine = ImitationEngine()
    engine.register_trader_model(
        trader_id="ptj",
        philosophy="crash_anticipation",
        risk_tolerance=0.3,
        preferred_regimes=["VOLATILE", "CRISIS"],
        entry_bias=-0.5,  # contrarian
        exit_discipline=0.9,
    )
    decision = engine.simulate(
        trader_id="ptj",
        market_regime="VOLATILE",
        trend_strength=-0.5,
        volatility=1.5,
        position_pnl=0.0,
        ts_ns=1000,
    )
    assert decision is not None
    assert decision.action == ImitationAction.BUY  # contrarian buy
    assert decision.conviction > 0


def test_performance_tracker():
    tracker = PerformanceTracker()
    for i in range(10):
        pnl = 0.01 if i < 7 else -0.005
        tracker.record(entity_id="atom_1", regime="TRENDING", pnl=pnl, ts_ns=i)
    summary = tracker.get_summary("atom_1")
    assert summary is not None
    assert summary.total_trades == 10
    assert summary.win_rate == 0.7
    assert summary.total_pnl > 0


def test_meta_controller_bridge():
    bridge = MetaControllerBridge()
    inp = bridge.build_input(
        regime="TRENDING_BULL",
        atom_fitness={"a1": 0.9, "a2": 0.7, "a3": 0.5},
        philosophy_vectors={"ptj": (0.5, 0.8, 0.3), "soros": (0.7, 0.6, 0.9)},
        reliability_scores={"ptj": 0.85, "soros": 0.9},
        narrative_alignment=0.7,
        cluster_weights={"macro": 0.4, "trend": 0.3, "quant": 0.3},
        divergences=["PTJ would sell here"],
        ts_ns=1000,
    )
    assert inp.regime_atoms[0] == "a1"
    assert inp.composition_confidence > 0
    payload = bridge.to_meta_controller_payload(inp)
    assert "trader_modeling" in payload
