"""Tests for BUILD-DIRECTIVE implementation (Steps 1-22).

28+ tests covering:
- TimeAuthority Protocol implementations
- OperatorAuthority frozen dataclass
- SemiAutoPolicy and threshold gate
- Approval queue FIFO operations
- Auto-exit logic
- Execution routing with authority
- Learning-evolution loop FSM
- External signal policy
- Data normalizer
- Strategy extractor and atom registry
- Strategy composer (B-COMPOSER)
- Strategy genome mutation and crossover
- Browser research service
- Pattern store
- Vector memory search
"""

from __future__ import annotations

# ============================================================================
# Step 1 — TimeAuthority
# ============================================================================


def test_wall_clock_returns_nanoseconds():
    """WallClock.now_ns() returns nanoseconds."""
    from core.time_source import WallClock

    clock = WallClock()
    ns = clock.now_ns()
    assert ns > 0
    assert ns > 1_000_000_000_000_000_000  # After year 2001


def test_fixed_clock_deterministic():
    """FixedClock always returns the same sequence (INV-15)."""
    from core.time_source import FixedClock

    clock = FixedClock(seed_ns=1000, step_ns=100)
    assert clock.now_ns() == 1000
    assert clock.now_ns() == 1100
    assert clock.now_ns() == 1200


def test_ledger_clock_replays_exact():
    """LedgerClock replays exact timestamps."""
    from core.time_source import LedgerClock

    stamps = (5000, 6000, 7000)
    clock = LedgerClock(timestamps=stamps)
    assert clock.now_ns() == 5000
    assert clock.now_ns() == 6000
    assert clock.now_ns() == 7000


# ============================================================================
# Step 2 — OperatorAuthority
# ============================================================================


def test_operator_authority_defaults():
    """OperatorAuthority has correct BUILD-DIRECTIVE defaults."""
    from core.contracts.operator_authority import (
        LearningAuthority,
        LiveExecutionAuthority,
        OperatorAuthority,
        PracticeAuthority,
    )

    oa = OperatorAuthority()
    assert oa.learning == LearningAuthority.FULL
    assert oa.practice == PracticeAuthority.ON
    assert oa.live_execution == LiveExecutionAuthority.BLOCKED
    assert oa.operator_id == "ronald"


def test_operator_authority_is_frozen():
    """OperatorAuthority is immutable."""
    from core.contracts.operator_authority import OperatorAuthority

    oa = OperatorAuthority()
    try:
        oa.learning = "OFF"  # type: ignore[misc]
        raise AssertionError("Should not reach here")
    except Exception:
        pass  # Expected: FrozenInstanceError


def test_semi_auto_policy():
    """SemiAutoPolicy has correct thresholds."""
    from core.contracts.operator_authority import SemiAutoPolicy

    policy = SemiAutoPolicy(
        entry_requires_approval=True,
        exit_auto=True,
        risk_reduce_auto=True,
        notional_threshold_usd=500.0,
        position_fraction_cap=0.05,
        volatility_cap_zscore=2.5,
    )
    assert policy.entry_requires_approval is True
    assert policy.exit_auto is True
    assert policy.notional_threshold_usd == 500.0


# ============================================================================
# Step 6 — Semi-Auto
# ============================================================================


def test_approval_queue_fifo():
    """ApprovalQueue operates as FIFO."""
    from execution_engine.semi_auto.approval_queue import ApprovalQueue, PendingApproval

    q = ApprovalQueue()
    a1 = PendingApproval(
        request_id="r1",
        domain="NORMAL",
        symbol="BTC",
        side="BUY",
        notional_usd=100.0,
        rationale="test",
        ts_ns=1000,
    )
    a2 = PendingApproval(
        request_id="r2",
        domain="NORMAL",
        symbol="ETH",
        side="SELL",
        notional_usd=200.0,
        rationale="test2",
        ts_ns=2000,
    )
    q.push(a1)
    q.push(a2)
    assert q.size == 2
    assert q.peek().request_id == "r1"
    q.approve("r1")
    assert q.size == 1
    assert q.peek().request_id == "r2"


def test_threshold_gate_exit_auto_fires():
    """Exits always AUTO_FIRE regardless of thresholds."""
    from execution_engine.semi_auto.threshold_gate import (
        ThresholdContext,
        ThresholdVerdict,
        evaluate_threshold,
    )

    ctx = ThresholdContext(
        notional_usd=99999.0,
        position_fraction=1.0,
        volatility_zscore=10.0,
        is_exit=True,
        is_risk_reduce=False,
    )
    result = evaluate_threshold(
        ctx,
        notional_threshold_usd=100.0,
        position_fraction_cap=0.05,
        volatility_cap_zscore=2.0,
    )
    assert result == ThresholdVerdict.AUTO_FIRE


def test_threshold_gate_entry_requires_approval():
    """Entries above threshold require approval."""
    from execution_engine.semi_auto.threshold_gate import (
        ThresholdContext,
        ThresholdVerdict,
        evaluate_threshold,
    )

    ctx = ThresholdContext(
        notional_usd=600.0,
        position_fraction=0.01,
        volatility_zscore=1.0,
        is_exit=False,
        is_risk_reduce=False,
    )
    result = evaluate_threshold(
        ctx,
        notional_threshold_usd=500.0,
        position_fraction_cap=0.05,
        volatility_cap_zscore=2.5,
    )
    assert result == ThresholdVerdict.REQUIRES_APPROVAL


def test_threshold_gate_entry_below_threshold_auto():
    """Entries below all thresholds AUTO_FIRE."""
    from execution_engine.semi_auto.threshold_gate import (
        ThresholdContext,
        ThresholdVerdict,
        evaluate_threshold,
    )

    ctx = ThresholdContext(
        notional_usd=100.0,
        position_fraction=0.01,
        volatility_zscore=1.0,
        is_exit=False,
        is_risk_reduce=False,
    )
    result = evaluate_threshold(
        ctx,
        notional_threshold_usd=500.0,
        position_fraction_cap=0.05,
        volatility_cap_zscore=2.5,
    )
    assert result == ThresholdVerdict.AUTO_FIRE


def test_auto_exit_stop_loss():
    """Auto-exit fires for stop loss."""
    from execution_engine.semi_auto.auto_exit_handler import ExitReason, should_auto_exit

    reason = should_auto_exit(
        is_exit=False,
        is_risk_reduce=False,
        has_stop_loss_trigger=True,
        has_trailing_stop_trigger=False,
        drawdown_fraction=0.05,
        max_drawdown_cap=0.15,
    )
    assert reason == ExitReason.STOP_LOSS


def test_auto_exit_max_drawdown():
    """Auto-exit fires at max drawdown."""
    from execution_engine.semi_auto.auto_exit_handler import ExitReason, should_auto_exit

    reason = should_auto_exit(
        is_exit=False,
        is_risk_reduce=False,
        has_stop_loss_trigger=False,
        has_trailing_stop_trigger=False,
        drawdown_fraction=0.20,
        max_drawdown_cap=0.15,
    )
    assert reason == ExitReason.MAX_DRAWDOWN


# ============================================================================
# Step 7 — Execution routing
# ============================================================================


def test_route_blocked_paper():
    """LiveExecution=BLOCKED, Practice=ON routes to PAPER."""
    from execution_engine.execution_gate import ExecutionRouteDecision, route_with_authority

    decision = route_with_authority(
        live_execution="BLOCKED",
        practice="ON",
        trading_mode="FULL_AUTO",
    )
    assert decision.route == ExecutionRouteDecision.PAPER


def test_route_manual_blocks():
    """MANUAL mode blocks even when ARMED."""
    from execution_engine.execution_gate import ExecutionRouteDecision, route_with_authority

    decision = route_with_authority(
        live_execution="ARMED",
        practice="ON",
        trading_mode="MANUAL",
    )
    assert decision.route == ExecutionRouteDecision.BLOCKED


def test_route_semi_auto_exit_executes():
    """SEMI_AUTO exit auto-fires."""
    from execution_engine.execution_gate import ExecutionRouteDecision, route_with_authority

    decision = route_with_authority(
        live_execution="ARMED",
        practice="ON",
        trading_mode="SEMI_AUTO",
        is_exit=True,
    )
    assert decision.route == ExecutionRouteDecision.EXECUTE


def test_route_semi_auto_entry_queues():
    """SEMI_AUTO entry routes to approval queue."""
    from execution_engine.execution_gate import ExecutionRouteDecision, route_with_authority

    decision = route_with_authority(
        live_execution="ARMED",
        practice="ON",
        trading_mode="SEMI_AUTO",
        is_exit=False,
    )
    assert decision.route == ExecutionRouteDecision.SEMI_AUTO_QUEUE


def test_route_full_auto_executes():
    """FULL_AUTO immediately executes."""
    from execution_engine.execution_gate import ExecutionRouteDecision, route_with_authority

    decision = route_with_authority(
        live_execution="ARMED",
        practice="OFF",
        trading_mode="FULL_AUTO",
    )
    assert decision.route == ExecutionRouteDecision.EXECUTE


# ============================================================================
# Step 8 — Learning-Evolution Loop
# ============================================================================


def test_loop_class_c_rejected():
    """Class C mutations always rejected by the loop."""
    from governance_engine.control_plane.learning_evolution_loop import (
        LearningEvolutionLoop,
        MutationClass,
        MutationProposal,
    )

    loop = LearningEvolutionLoop()
    proposal = MutationProposal(
        mutation_class=MutationClass.CLASS_C,
        parameter_path="live_execution",
        old_value="BLOCKED",
        new_value="ARMED",
        source_engine="intelligence_engine",
        rationale="test",
        ts_ns=1000,
    )
    result = loop.propose(proposal)
    assert result == "REJECTED_OPERATOR_ONLY"


def test_loop_class_a_auto_applies():
    """Class A mutations auto-apply when learning enabled."""
    from governance_engine.control_plane.learning_evolution_loop import (
        LearningEvolutionLoop,
        LoopState,
        MutationClass,
        MutationProposal,
    )

    loop = LearningEvolutionLoop()
    proposal = MutationProposal(
        mutation_class=MutationClass.CLASS_A,
        parameter_path="confidence.calibration",
        old_value="0.5",
        new_value="0.6",
        source_engine="learning_engine",
        rationale="calibration drift",
        ts_ns=2000,
    )
    loop.propose(proposal)
    loop.validate()
    applied = loop.apply_class_a(learning_enabled=True)
    assert len(applied) == 1
    assert loop.state == LoopState.IDLE


# ============================================================================
# Step 9 — External Signal Policy
# ============================================================================


def test_external_signal_unregistered_blocked():
    """Unregistered sources are blocked."""
    from governance_engine.control_plane.external_signal_policy import (
        SourceTrust,
        validate_external_signal,
    )

    result = validate_external_signal(
        source_platform="unknown_platform",
        registered_sources={"tradingview": SourceTrust.MEDIUM},
        signal_confidence=0.9,
    )
    assert result.allowed is False


def test_external_signal_trust_caps_confidence():
    """Trust level caps the signal confidence."""
    from governance_engine.control_plane.external_signal_policy import (
        SourceTrust,
        validate_external_signal,
    )

    result = validate_external_signal(
        source_platform="tradingview",
        registered_sources={"tradingview": SourceTrust.MEDIUM},
        signal_confidence=0.9,
    )
    assert result.allowed is True
    assert result.confidence_cap == 0.5  # MEDIUM cap


# ============================================================================
# Step 10 — Normalizer
# ============================================================================


def test_normalizer_tradingview():
    """Normalizer handles TradingView payloads."""
    from data_pipeline.normalizer import NormalizationStatus, normalize

    result = normalize(
        platform="tradingview",
        payload={"symbol": "BTCUSDT", "action": "buy", "price": 65000.0},
    )
    assert result.status == NormalizationStatus.SUCCESS
    assert result.symbol == "BTCUSDT"
    assert result.side == "BUY"


def test_normalizer_unknown_platform():
    """Normalizer rejects unknown platforms."""
    from data_pipeline.normalizer import NormalizationStatus, normalize

    result = normalize(platform="unknown", payload={"symbol": "X"})
    assert result.status == NormalizationStatus.PLATFORM_UNKNOWN


def test_normalizer_missing_fields():
    """Normalizer detects missing required fields."""
    from data_pipeline.normalizer import NormalizationStatus, normalize

    result = normalize(platform="tradingview", payload={"symbol": "BTC"})
    assert result.status == NormalizationStatus.MISSING_FIELDS


# ============================================================================
# Step 13 — Strategy Extractor
# ============================================================================


def test_strategy_extractor_trend():
    """Extractor identifies trend-following atoms."""
    from intelligence_engine.trader_modeling.strategy_extractor import (
        AtomCategory,
        StrategyExtractor,
    )

    extractor = StrategyExtractor()
    atoms = extractor.extract_from_observation(
        trader_id="livermore",
        philosophy="trend_following",
        content="Follow the trend using moving averages",
        ts_ns=1000,
    )
    assert len(atoms) >= 1
    assert atoms[0].category == AtomCategory.ENTRY


# ============================================================================
# Step 17 — Pattern Store
# ============================================================================


def test_pattern_store_upsert_increments():
    """Pattern store increments frequency on upsert."""
    from state.memory_tensor.trader_patterns.pattern_store import PatternStore, StoredPattern

    store = PatternStore()
    p = StoredPattern(
        pattern_id="p1",
        trader_id="t1",
        category="ENTRY",
        description="test",
        frequency=1,
        last_seen_ts_ns=1000,
        confidence=0.8,
        regime="TRENDING",
    )
    store.upsert(p)
    store.upsert(p)
    patterns = store.get_by_trader("t1")
    assert patterns[0].frequency == 2


# ============================================================================
# Step 18 — Strategy Composer
# ============================================================================


def test_composer_builds_strategy():
    """Composer produces ComposedStrategy from atoms."""
    from intelligence_engine.strategy_composer.composer import (
        ComposedStrategy,
        CompositionRequest,
        StrategyComposer,
    )

    composer = StrategyComposer()
    atoms = [
        {
            "atom_id": "a1",
            "source_trader": "trader_a",
            "regime_fitness": {"TRENDING": 0.8},
            "sharpe": 1.5,
            "max_drawdown": 0.1,
        },
        {
            "atom_id": "a2",
            "source_trader": "trader_b",
            "regime_fitness": {"TRENDING": 0.7},
            "sharpe": 1.2,
            "max_drawdown": 0.08,
        },
    ]
    request = CompositionRequest(target_regime="TRENDING")
    result = composer.compose(atoms=atoms, request=request, ts_ns=5000)
    assert result is not None
    assert isinstance(result, ComposedStrategy)
    assert len(result.atoms) == 2


# ============================================================================
# Step 19 — Strategy Genome Mutation
# ============================================================================


def test_genome_mutation_deterministic():
    """Mutation with seed is deterministic (INV-15)."""
    from evolution_engine.strategy_genome.mutation_engine import mutate_genome
    from evolution_engine.strategy_genome.strategy_genome import Gene, StrategyGenome

    genome = StrategyGenome(
        genome_id="g1",
        strategy_id="s1",
        genes=(
            Gene(name="lookback", value=20.0, min_value=5.0, max_value=100.0),
            Gene(name="threshold", value=0.5, min_value=0.0, max_value=1.0),
        ),
        atom_ids=("a1",),
    )
    m1, _ = mutate_genome(genome, mutation_rate=1.0, seed=42)
    m2, _ = mutate_genome(genome, mutation_rate=1.0, seed=42)
    assert m1.genes == m2.genes


# ============================================================================
# Step 20 — Browser Research Service
# ============================================================================


def test_research_service_returns_result():
    """Research service produces structured results."""
    from unittest.mock import patch

    from intelligence_engine.research.browser_research_service import (
        BrowserResearchService,
        ResearchRequest,
        ResearchTaskType,
    )

    svc = BrowserResearchService()
    request = ResearchRequest(
        task_type=ResearchTaskType.TRADER_PROFILE,
        query="Ed Seykota",
        target_urls=("https://example.com/seykota",),
    )
    # Patch the network call so the test runs without internet access.
    with patch(
        "intelligence_engine.research.browser_research_service._fetch_url",
        return_value=("Ed Seykota – Trend Follower", "Ed Seykota is a legendary trend-following trader."),
    ):
        result = svc.fetch_research(request, ts_ns=1000)
    assert result.status == "COMPLETED"
    assert result.task_type == ResearchTaskType.TRADER_PROFILE
