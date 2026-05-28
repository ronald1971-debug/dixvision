"""Tests for runtime fabric, governance, and replay (CONVERGENCE PILLARS 2-4)."""

from __future__ import annotations

import asyncio

# ============================================================================
# Pillar 2 — Execution Fabric
# ============================================================================


def test_ingestion_bus_backpressure():
    """Ingestion bus rejects ticks when queue is full."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.fabric.ingestion_bus import IngestedTick, IngestionBus, IngestionSource

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("execution_fabric")
    bus = IngestionBus(store=store, writer_token=token, queue_size=2)

    tick = IngestedTick(
        source=IngestionSource.BINANCE_WS,
        symbol="BTCUSDT",
        price=65000.0,
        volume=1.0,
        ts_ns=1000,
    )

    # Fill queue
    loop = asyncio.new_event_loop()
    accepted1 = loop.run_until_complete(bus.ingest(tick))
    accepted2 = loop.run_until_complete(bus.ingest(tick))
    assert accepted1 is True
    assert accepted2 is True

    # Third should fail (backpressure)
    accepted3 = loop.run_until_complete(bus.ingest(tick))
    assert accepted3 is False
    assert bus.metrics.ticks_dropped == 1
    loop.close()


def test_decision_pipeline_blocks_when_frozen():
    """Decision pipeline produces no intents when frozen."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.fabric.decision_pipeline import DecisionPipeline
    from runtime.fabric.ingestion_bus import IngestedTick, IngestionSource

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("governance_engine")
    token.write(1000, freeze_active=True)

    pipeline = DecisionPipeline(store=store)
    tick = IngestedTick(
        source=IngestionSource.BINANCE_WS,
        symbol="BTCUSDT",
        price=65000.0,
        volume=1.0,
        ts_ns=2000,
    )
    result = pipeline.process_tick(tick)
    assert result is None
    assert pipeline.metrics.signals_filtered == 1


def test_execution_router_blocked_paper():
    """Router sends to paper when live_execution blocked + practice ON."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.fabric.decision_pipeline import (
        DecisionSignal,
        ExecutionIntent,
        SignalStrength,
    )
    from runtime.fabric.execution_router import ExecutionRouter, RouteDecision

    store = RuntimeAuthorityStore()
    router = ExecutionRouter(store=store)

    signal = DecisionSignal(
        symbol="BTCUSDT",
        side="BUY",
        strength=SignalStrength.STRONG,
        confidence=0.9,
        source_engine="test",
        rationale="test",
        ts_ns=1000,
    )
    intent = ExecutionIntent(
        intent_id="i1",
        symbol="BTCUSDT",
        side="BUY",
        notional_usd=500.0,
        domain="NORMAL",
        signal=signal,
        ts_ns=1000,
    )

    result = router.route(intent)
    assert result.decision == RouteDecision.PAPER
    assert router.metrics.paper_count == 1


def test_fill_reconciler_matches_order():
    """Reconciler matches fill to pending order."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.fabric.fill_reconciler import Fill, FillReconciler, FillStatus

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("execution_fabric")
    reconciler = FillReconciler(store=store, writer_token=token)

    reconciler.register_order(order_id="o1", symbol="BTCUSDT", side="BUY", expected_quantity=1.0)

    fill = Fill(
        fill_id="f1",
        order_id="o1",
        symbol="BTCUSDT",
        side="BUY",
        quantity=1.0,
        price=65000.0,
        fee_usd=6.5,
        ts_ns=3000,
        adapter_name="binance",
    )
    result = reconciler.reconcile(fill)
    assert result.status == FillStatus.MATCHED
    assert store.snapshot.open_positions == 1


def test_fill_reconciler_unexpected_fill():
    """Reconciler flags unexpected fills."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.fabric.fill_reconciler import Fill, FillReconciler, FillStatus

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("execution_fabric")
    reconciler = FillReconciler(store=store, writer_token=token)

    fill = Fill(
        fill_id="f1",
        order_id="unknown",
        symbol="ETH",
        side="SELL",
        quantity=10.0,
        price=3500.0,
        fee_usd=3.5,
        ts_ns=4000,
        adapter_name="binance",
    )
    result = reconciler.reconcile(fill)
    assert result.status == FillStatus.UNEXPECTED


def test_risk_snapshotter_healthy():
    """Risk snapshotter reports healthy when no exposure."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.fabric.risk_snapshotter import RiskSnapshotter

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("execution_fabric")
    risk = RiskSnapshotter(store=store, writer_token=token)

    metrics = risk.compute(ts_ns=5000)
    assert metrics.health_score == 1.0
    assert metrics.risk_factors == ()


# ============================================================================
# Pillar 3 — Live Governance Enforcement
# ============================================================================


def test_enforcement_gate_allow():
    """Gate allows when no policies registered."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.governance.enforcement_gate import EnforcementGate

    store = RuntimeAuthorityStore()
    gate = EnforcementGate(store=store)

    result = gate.enforce(intent_id="i1", intent_data={"symbol": "BTC"}, ts_ns=1000)
    assert result.passed is True
    assert result.decision.verdict.value == "allow"


def test_enforcement_gate_deny_frozen():
    """Gate denies when freeze policy is active."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.governance.enforcement_gate import EnforcementGate, FreezeBlockPolicy

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("governance_engine")
    token.write(1000, freeze_active=True)

    gate = EnforcementGate(store=store)
    gate.register_policy(FreezeBlockPolicy())

    result = gate.enforce(intent_id="i1", intent_data={"symbol": "BTC"}, ts_ns=2000)
    assert result.passed is False
    assert "frozen" in result.decision.reason


def test_enforcement_gate_signature_verification():
    """Gate produces verifiable HMAC signatures."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.governance.enforcement_gate import EnforcementGate

    store = RuntimeAuthorityStore()
    gate = EnforcementGate(store=store)

    result = gate.enforce(intent_id="i1", intent_data={"symbol": "BTC"}, ts_ns=1000)
    assert gate.verify_signature(result.decision) is True


def test_enforcement_gate_health_threshold():
    """Gate denies when health below threshold."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.governance.enforcement_gate import EnforcementGate, HealthThresholdPolicy

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("governance_engine")
    token.write(1000, health_score=0.1)

    gate = EnforcementGate(store=store)
    gate.register_policy(HealthThresholdPolicy(min_health=0.3))

    result = gate.enforce(intent_id="i1", intent_data={"symbol": "BTC"}, ts_ns=2000)
    assert result.passed is False
    assert "health" in result.decision.reason


def test_deterministic_arbiter_same_input_same_hash():
    """Same inputs produce same hash."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.governance.deterministic_arbiter import canonicalize_input

    store = RuntimeAuthorityStore()
    snap = store.snapshot

    input1 = canonicalize_input(
        intent_id="i1", intent_data={"symbol": "BTC", "side": "BUY"}, snapshot=snap
    )
    input2 = canonicalize_input(
        intent_id="i1", intent_data={"symbol": "BTC", "side": "BUY"}, snapshot=snap
    )
    assert input1.intent_data_hash == input2.intent_data_hash


# ============================================================================
# Pillar 4 — Replay Determinism
# ============================================================================


def test_session_recorder_basic():
    """Recorder captures events and produces manifest."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.replay.session_recorder import EventCategory, SessionRecorder

    store = RuntimeAuthorityStore()
    recorder = SessionRecorder(session_id="test-1", store=store)

    recorder.start(ts_ns=1000)
    recorder.record(
        category=EventCategory.MARKET_TICK,
        ts_ns=2000,
        payload={"symbol": "BTC", "price": 65000},
    )
    recorder.record(
        category=EventCategory.GOVERNANCE_DECISION,
        ts_ns=3000,
        payload={"intent_id": "i1", "verdict": "ALLOW"},
    )
    manifest = recorder.stop(ts_ns=4000)

    # 2 explicit + 2 checkpoints (start + stop)
    assert manifest.total_events == 4
    assert manifest.session_id == "test-1"
    assert manifest.integrity_hash != ""


def test_session_replay_identical():
    """Replay of clean recording produces IDENTICAL result."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.replay.session_recorder import EventCategory, SessionRecorder
    from runtime.replay.session_replayer import ReplayStatus, SessionReplayer

    store = RuntimeAuthorityStore()
    recorder = SessionRecorder(session_id="test-2", store=store)
    recorder.start(ts_ns=1000)
    recorder.record(
        category=EventCategory.MARKET_TICK,
        ts_ns=2000,
        payload={"symbol": "BTC", "price": 65000},
    )
    manifest = recorder.stop(ts_ns=3000)

    # Replay
    replayer = SessionReplayer()
    result = replayer.replay(events=recorder.get_events(), manifest=manifest)
    assert result.status == ReplayStatus.IDENTICAL
    assert result.divergences == ()


def test_divergence_analysis():
    """Divergence detector classifies issues."""
    from runtime.replay.divergence_detector import DivergenceCause, analyze_divergences
    from runtime.replay.session_replayer import Divergence, ReplayResult, ReplayStatus

    result = ReplayResult(
        status=ReplayStatus.DIVERGED,
        events_replayed=100,
        checkpoints_verified=9,
        divergences=(
            Divergence(
                event_sequence=50,
                ts_ns=5000,
                field="health_score",
                expected="0.9",
                actual="0.7",
            ),
        ),
        final_state_version=100,
    )

    analysis = analyze_divergences(result)
    assert analysis.total_divergences == 1
    assert analysis.first_divergence_at == 50
    assert analysis.reports[0].probable_cause == DivergenceCause.STATE_MUTATION_ORDER
