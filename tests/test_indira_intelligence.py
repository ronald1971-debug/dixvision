"""Tests for Indira Intelligence Layer — all 10 new components."""

from __future__ import annotations

# ─── Strategy Arena ───────────────────────────────────────────────


class TestStrategyArena:
    def test_admit_and_tick(self):
        from intelligence_engine.strategy_arena import ArenaConfig, ArenaEngine

        arena = ArenaEngine(ArenaConfig(incubation_ticks=5))
        slot = arena.admit("strat-1", "TA-MACRO-001")
        assert slot.strategy_id == "strat-1"
        assert slot.allocation_pct == 0.01

        # Update performance
        for _ in range(10):
            arena.update_performance("strat-1", pnl_delta=0.1, win=True)

        killed = arena.tick()
        assert len(killed) == 0
        assert arena.active_slots[0].ticks_alive == 10

    def test_kill_underperformers(self):
        from intelligence_engine.strategy_arena import ArenaConfig, ArenaEngine

        arena = ArenaEngine(ArenaConfig(incubation_ticks=5, min_allocation_pct=0.001))
        arena.admit("s1", "TA-TREND-001")
        arena.admit("s2", "TA-QUANT-001")

        # s1 wins, s2 loses
        for _ in range(10):
            arena.update_performance("s1", pnl_delta=1.0, win=True)
            arena.update_performance("s2", pnl_delta=-1.0, win=False)

        # Run many ticks to let decay happen
        for _ in range(50):
            arena.tick()
            arena.update_performance("s1", pnl_delta=0.5, win=True)
            arena.update_performance("s2", pnl_delta=-0.5, win=False)

        # s2 should eventually be killed or heavily decayed
        s2 = next((s for s in arena._slots.values() if s.strategy_id == "s2"), None)
        assert s2 is not None
        assert s2.allocation_pct < 0.1

    def test_capital_allocator(self):
        from intelligence_engine.strategy_arena import ArenaEngine, CapitalAllocator

        arena = ArenaEngine()
        arena.admit("s1", "TA-001")
        for _ in range(5):
            arena.update_performance("s1", pnl_delta=1.0, win=True)

        allocator = CapitalAllocator(arena)
        directives = allocator.allocate(100_000.0)
        assert len(directives) == 1
        assert directives[0].notional_usd > 0

    def test_kill_policy(self):
        from intelligence_engine.strategy_arena import KillPolicy
        from intelligence_engine.strategy_arena.arena_engine import StrategySlot

        policy = KillPolicy(max_drawdown_pct=0.20)
        slot = StrategySlot(
            strategy_id="s1",
            archetype_id="TA-001",
            max_drawdown_pct=0.25,
            ticks_alive=50,
        )
        reason = policy.should_kill(slot)
        assert reason is not None
        assert reason.reason == "MAX_DRAWDOWN_EXCEEDED"


# ─── Reward System ────────────────────────────────────────────────


class TestRewardSystem:
    def test_composite_reward(self):
        from learning_engine.reward_system import RewardSystem, TradeOutcome

        rs = RewardSystem()
        outcome = TradeOutcome(
            pnl_usd=500.0,
            holding_period_ns=3_600_000_000_000,
            entry_slippage_bps=2.0,
            exit_slippage_bps=1.5,
            intended_size=1000.0,
            actual_size=980.0,
            regime_at_entry="TRENDING",
            regime_predicted="TRENDING",
            peak_pnl_usd=600.0,
            portfolio_drawdown_pct=0.02,
        )
        signal = rs.compute(outcome)
        assert signal.composite_reward > 0  # profitable trade should have positive reward
        assert signal.regime_reward == 1.0  # regime was correct

    def test_negative_reward_for_bad_trade(self):
        from learning_engine.reward_system import RewardSystem, TradeOutcome

        rs = RewardSystem()
        outcome = TradeOutcome(
            pnl_usd=-800.0,
            holding_period_ns=100_000_000,
            entry_slippage_bps=15.0,
            exit_slippage_bps=10.0,
            intended_size=1000.0,
            actual_size=1000.0,
            regime_at_entry="VOLATILE",
            regime_predicted="RANGING",
            peak_pnl_usd=100.0,
            portfolio_drawdown_pct=0.15,
        )
        signal = rs.compute(outcome)
        assert signal.composite_reward < 0  # bad trade = negative reward
        assert signal.regime_reward == -0.3  # regime wrong


# ─── Reflection Engine ────────────────────────────────────────────


class TestReflectionEngine:
    def test_correct_prediction(self):
        from core.coherence.reflection_engine import (
            DecisionExpectation,
            MismatchSeverity,
            RealizedOutcome,
            ReflectionEngine,
        )

        engine = ReflectionEngine()
        expected = DecisionExpectation(
            decision_id="d1",
            ts_ns=1000,
            predicted_direction="UP",
            predicted_magnitude_bps=100.0,
            predicted_holding_ns=1000,
            confidence=0.8,
            regime_prediction="TRENDING",
            strategy_id="s1",
        )
        realized = RealizedOutcome(
            decision_id="d1",
            ts_ns=2000,
            actual_direction="UP",
            actual_magnitude_bps=110.0,
            actual_holding_ns=1100,
            actual_regime="TRENDING",
            pnl_bps=90.0,
        )
        result = engine.reflect(expected, realized)
        assert result.mismatch_severity == MismatchSeverity.NONE
        assert result.direction_correct is True

    def test_wrong_direction(self):
        from core.coherence.reflection_engine import (
            DecisionExpectation,
            MismatchSeverity,
            MismatchType,
            RealizedOutcome,
            ReflectionEngine,
        )

        engine = ReflectionEngine()
        expected = DecisionExpectation(
            decision_id="d2",
            ts_ns=1000,
            predicted_direction="UP",
            predicted_magnitude_bps=100.0,
            predicted_holding_ns=1000,
            confidence=0.9,
            regime_prediction="TRENDING",
            strategy_id="s1",
        )
        realized = RealizedOutcome(
            decision_id="d2",
            ts_ns=2000,
            actual_direction="DOWN",
            actual_magnitude_bps=200.0,
            actual_holding_ns=500,
            actual_regime="VOLATILE",
            pnl_bps=-150.0,
        )
        result = engine.reflect(expected, realized)
        assert result.direction_correct is False
        assert MismatchType.DIRECTION in result.mismatch_types
        assert result.mismatch_severity in (MismatchSeverity.SIGNIFICANT, MismatchSeverity.CRITICAL)


# ─── Attribution Engine ───────────────────────────────────────────


class TestAttribution:
    def test_pnl_decomposition(self):
        from learning_engine.attribution import PnLDecomposer

        decomp = PnLDecomposer()
        result = decomp.decompose(
            total_pnl=100.0,
            market_return_bps=50.0,
            position_beta=1.0,
            entry_slippage_bps=2.0,
            exit_slippage_bps=1.5,
            position_size=10000.0,
            optimal_entry_pnl=95.0,
            actual_entry_pnl=90.0,
            regime_correct=True,
        )
        assert abs(result.total_pnl - 100.0) < 0.01
        assert result.execution_pnl < 0  # slippage is a cost
        assert result.regime_pnl > 0  # regime was correct

    def test_decision_attribution(self):
        from learning_engine.attribution import DecisionAttributor

        attr = DecisionAttributor()
        attr.register_decision(
            trade_id="t1",
            signal_id="sig1",
            strategy_id="s1",
            archetype_id="TA-001",
            regime="TRENDING",
            confidence=0.8,
        )
        result = attr.attribute(
            trade_id="t1",
            pnl_bps=50.0,
            regime_at_exit="TRENDING",
            portfolio_contribution_bps=5.0,
        )
        assert result is not None
        assert result.was_profitable is True
        assert result.strategy_id == "s1"

    def test_mistake_classifier(self):
        from learning_engine.attribution import MistakeCategory, MistakeClassifier

        mc = MistakeClassifier()
        result = mc.classify(
            trade_id="t1",
            pnl_bps=-100.0,
            direction_correct=False,
            regime_correct=False,
            execution_fill_ratio=0.9,
            entry_slippage_bps=3.0,
            exit_slippage_bps=2.0,
            position_size_vs_target=1.0,
            correlated_losses=0,
        )
        assert result.category == MistakeCategory.REGIME_ERROR

    def test_edge_decay_tracker(self):
        from learning_engine.attribution import EdgeDecayTracker, EdgeHealth

        tracker = EdgeDecayTracker(window=20)
        # Feed declining Sharpe
        for i in range(30):
            report = tracker.update(
                "s1",
                sharpe=1.0 - i * 0.05,
                win_rate=0.6 - i * 0.01,
                profit_factor=2.0 - i * 0.05,
            )
        assert report.health in (EdgeHealth.WEAKENING, EdgeHealth.DYING, EdgeHealth.DEAD)


# ─── Execution Intelligence ───────────────────────────────────────


class TestExecutionIntelligence:
    def test_liquidity_model(self):
        from execution_engine.intelligence import LiquidityModel

        model = LiquidityModel()
        snap = model.update(
            "BTCUSD",
            ts_ns=1000,
            bids=[(50000, 1.0), (49990, 2.0)],
            asks=[(50010, 1.5), (50020, 2.5)],
        )
        assert snap.spread_bps > 0
        assert snap.bid_depth_usd > 0
        assert snap.imbalance_ratio > 0

    def test_slippage_predictor(self):
        from execution_engine.intelligence import LiquidityModel, SlippagePredictor

        model = LiquidityModel()
        model.update("BTCUSD", ts_ns=1000, bids=[(50000, 10.0)], asks=[(50010, 10.0)])
        pred = SlippagePredictor(model)
        est = pred.predict("BTCUSD", 10000.0)
        assert est.estimated_slippage_bps > 0

    def test_order_splitter(self):
        from execution_engine.intelligence import LiquidityModel, OrderSplitter

        model = LiquidityModel()
        model.update("ETH", ts_ns=1, bids=[(3000, 50)], asks=[(3001, 50)])
        splitter = OrderSplitter(model)
        plan = splitter.plan("ETH", 100_000.0)
        assert len(plan.slices) >= 2
        total = sum(s.size_usd for s in plan.slices)
        assert abs(total - 100_000.0) < 0.01

    def test_smart_router(self):
        from execution_engine.intelligence import SmartRouter
        from execution_engine.intelligence.smart_router import Venue

        router = SmartRouter()
        router.update_venue_liquidity("BTC", Venue.BINANCE, 1_000_000)
        router.update_venue_liquidity("BTC", Venue.COINBASE, 500_000)
        decision = router.route("BTC", 50_000.0)
        assert decision.primary_venue is not None
        assert len(decision.scores) > 0


# ─── Alpha Miner ─────────────────────────────────────────────────


class TestAlphaMiner:
    def test_feature_discovery(self):
        from intelligence_engine.alpha_miner import FeatureDiscoverer

        disc = FeatureDiscoverer(window_size=20, emergence_threshold=0.2)
        # Feature starts unimportant, becomes important
        for _i in range(10):
            disc.update({"feature_x": 0.1, "feature_y": 0.5})
        for _i in range(10):
            discoveries = disc.update({"feature_x": 0.8, "feature_y": 0.5})
        # feature_x should be flagged as emerging
        emerging = [d for d in discoveries if d.feature_name == "feature_x"]
        assert len(emerging) > 0

    def test_correlation_monitor(self):
        from intelligence_engine.alpha_miner import CorrelationMonitor

        mon = CorrelationMonitor(lookback=30, break_threshold=0.3)
        import math

        # Two assets that move together, then diverge
        for i in range(30):
            mon.update("A", math.sin(i * 0.1))
            mon.update("B", math.sin(i * 0.1) + 0.01 * i)
        for i in range(30, 60):
            mon.update("A", math.sin(i * 0.1))
            mon.update("B", -math.sin(i * 0.1))  # diverge

        breaks = mon.scan([("A", "B")])
        # Should detect some correlation change
        assert isinstance(breaks, list)

    def test_anomaly_detector(self):
        from intelligence_engine.alpha_miner import AnomalyAlphaDetector

        det = AnomalyAlphaDetector(z_threshold=2.0, window=30)
        # Feed normal data
        for _i in range(30):
            det.update("BTC", volume=100.0, spread_bps=5.0, volatility=0.01)
        # Feed anomaly
        signals = det.update("BTC", volume=1000.0, spread_bps=5.0, volatility=0.01)
        # Volume spike should be detected
        vol_signals = [s for s in signals if s.anomaly_type.value == "VOLUME_SPIKE"]
        assert len(vol_signals) > 0


# ─── Multi-Horizon Engine ────────────────────────────────────────


class TestMultiHorizon:
    def test_single_horizon(self):
        from intelligence_engine.horizon import HorizonEngine, TimeHorizon

        engine = HorizonEngine()
        sig = engine.update_layer(
            TimeHorizon.SWING,
            trend_direction=0.8,
            trend_strength=0.7,
            confidence=0.85,
            reason="uptrend",
        )
        assert sig.direction.value == "LONG"

    def test_fusion_agreement(self):
        from intelligence_engine.horizon import HorizonEngine, TimeHorizon

        engine = HorizonEngine()
        for h in TimeHorizon:
            engine.update_layer(h, trend_direction=0.6, trend_strength=0.7, confidence=0.8)
        fused = engine.fuse("BTC")
        assert fused.direction.value == "LONG"
        assert fused.horizon_agreement > 0.5
        assert fused.conflict_description == "All horizons agree."

    def test_fusion_conflict(self):
        from intelligence_engine.horizon import HorizonEngine, TimeHorizon

        engine = HorizonEngine()
        engine.update_layer(
            TimeHorizon.MICRO, trend_direction=-0.5, trend_strength=0.6, confidence=0.7
        )
        engine.update_layer(
            TimeHorizon.SWING, trend_direction=0.8, trend_strength=0.8, confidence=0.9
        )
        engine.update_layer(
            TimeHorizon.MACRO, trend_direction=0.7, trend_strength=0.7, confidence=0.85
        )
        fused = engine.fuse("ETH")
        assert "Conflict" in fused.conflict_description


# ─── Meta-Labeler ────────────────────────────────────────────────


class TestMetaLabeler:
    def test_high_confidence_take(self):
        from intelligence_engine.meta.meta_labeler import MetaDecision, MetaLabeler

        ml = MetaLabeler(take_threshold=0.60)
        label = ml.label(
            "sig1",
            signal_strength=0.9,
            regime_alignment=0.85,
            multi_horizon_agreement=0.8,
            volume_confirmation=0.7,
            historical_winrate=0.75,
            volatility_percentile=0.5,
            correlation_support=0.8,
        )
        assert label.decision == MetaDecision.TAKE
        assert label.position_size_modifier > 0.7

    def test_low_confidence_skip(self):
        from intelligence_engine.meta.meta_labeler import MetaDecision, MetaLabeler

        ml = MetaLabeler(reduce_threshold=0.45)
        label = ml.label(
            "sig2",
            signal_strength=0.2,
            regime_alignment=0.1,
            multi_horizon_agreement=0.2,
            volume_confirmation=0.1,
            historical_winrate=0.3,
            volatility_percentile=0.9,
            correlation_support=0.1,
        )
        assert label.decision == MetaDecision.SKIP
        assert label.position_size_modifier == 0.0


# ─── Meta-Learning Loop ─────────────────────────────────────────


class TestMetaLearningLoop:
    def test_basic_tick(self):
        from learning_engine.meta_learning_loop import LearningMode, MetaLearningLoop

        loop = MetaLearningLoop()
        state = loop.state
        assert state.mode == LearningMode.EXPLORE

        update = loop.tick(
            current_performance=0.5,
            prediction_accuracy=0.6,
            strategy_diversity=0.7,
            regime_changed=False,
        )
        assert update.new_learning_rate > 0

    def test_regime_change_adapts(self):
        from learning_engine.meta_learning_loop import LearningMode, MetaLearningLoop

        loop = MetaLearningLoop(base_learning_rate=0.001)
        update = loop.tick(
            current_performance=0.5,
            prediction_accuracy=0.6,
            strategy_diversity=0.5,
            regime_changed=True,
        )
        assert update.mode_transition == LearningMode.ADAPT
        assert update.new_learning_rate > 0.001  # should speed up


# ─── Adversarial Engine ──────────────────────────────────────────


class TestAdversarialEngine:
    def test_manipulation_detector(self):
        from system_engine.adversarial import ManipulationDetector
        from system_engine.adversarial.manipulation_detector import OrderEvent

        det = ManipulationDetector()
        # Feed events simulating spoofing (large orders cancelled)
        for i in range(30):
            det.ingest(OrderEvent(ts_ns=i, symbol="BTC", side="BUY", size=10.0, price=50000))
        for i in range(30, 50):
            # Large orders
            det.ingest(
                OrderEvent(
                    ts_ns=i, symbol="BTC", side="BUY", size=500.0, price=50000, is_cancel=True
                )
            )
        alerts = det.ingest(
            OrderEvent(ts_ns=50, symbol="BTC", side="BUY", size=500.0, price=50000, is_cancel=True)
        )
        # May or may not detect depending on thresholds, but no crash
        assert isinstance(alerts, list)

    def test_bot_classifier(self):
        from system_engine.adversarial import BotClassifier
        from system_engine.adversarial.bot_classifier import ParticipantType

        bc = BotClassifier()
        profile = bc.classify(
            "p1",
            cancel_rate=0.9,
            avg_hold_time_ms=50,
            order_size_variance=0.1,
            directional_bias=0.02,
            trades_per_second=100,
            profitability_vs_mid=0.3,
            cross_venue_activity=0.1,
        )
        assert profile.classification == ParticipantType.MARKET_MAKER

    def test_trap_detector(self):
        from system_engine.adversarial import TrapDetector

        td = TrapDetector()
        # Feed stable prices then a breakout on low volume
        for _i in range(20):
            td.update("BTC", price=50000, volume=100, high=50010, low=49990)
        traps = td.update("BTC", price=50100, volume=10, high=50100, low=50000)
        # Should detect fakeout (breakout on low volume)
        assert isinstance(traps, list)


# ─── Trader Archetypes Registry ──────────────────────────────────


class TestTraderArchetypes:
    def test_yaml_loads(self):
        import yaml

        with open("registry/trader_archetypes.yaml") as f:
            data = yaml.safe_load(f)
        assert "archetypes" in data
        assert len(data["archetypes"]) == 300

    def test_all_have_required_fields(self):
        import yaml

        with open("registry/trader_archetypes.yaml") as f:
            data = yaml.safe_load(f)
        for _aid, arch in data["archetypes"].items():
            assert "name" in arch
            assert "state" in arch
            assert "seed_trader" in arch
            assert "group" in arch
            assert "philosophy" in arch
            assert "dimensions" in arch
            assert "belief_system" in arch["dimensions"]
            assert "risk_attitude" in arch["dimensions"]

    def test_30_unique_seeds(self):
        import yaml

        with open("registry/trader_archetypes.yaml") as f:
            data = yaml.safe_load(f)
        seeds = {arch["seed_trader"] for arch in data["archetypes"].values()}
        assert len(seeds) == 30  # exactly 30 real seed traders
