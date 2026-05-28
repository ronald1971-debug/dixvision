"""Tests for OSS integration batch 2 — OpenTelemetry, DuckDB, Temporal, Feast."""

from integrations.duckdb_adapter.analytics import (
    AnalyticsTable,
    DuckDBAnalyticsAdapter,
)
from integrations.feast_adapter.features import (
    FEATURE_REGISTRY,
    FeastFeatureAdapter,
    FeatureGroup,
)
from integrations.otel_adapter.metrics import (
    OTelMetricsAdapter,
)
from integrations.otel_adapter.tracing import (
    OTelTracingAdapter,
    SpanStatus,
)
from integrations.temporal_adapter.workflows import (
    TemporalWorkflowAdapter,
    WorkflowStatus,
    WorkflowType,
)

# --- OpenTelemetry Tracing Tests ---


def test_otel_start_end_span():
    tracer = OTelTracingAdapter()
    span_id = tracer.start_span("test.operation")
    assert tracer.active_span_count == 1

    span = tracer.end_span(span_id, status=SpanStatus.OK)
    assert span is not None
    assert span.name == "test.operation"
    assert span.status == SpanStatus.OK
    assert tracer.active_span_count == 0
    assert tracer.total_spans == 1


def test_otel_span_attributes():
    tracer = OTelTracingAdapter()
    span_id = tracer.start_span(
        "intelligence.decision",
        attributes={"symbol": "BTC", "confidence": 0.9},
    )
    tracer.set_attribute(span_id, "regime", "TRENDING_BULL")
    tracer.end_span(span_id)

    spans = tracer.get_recent_spans()
    assert spans[0].attributes["regime"] == "TRENDING_BULL"


def test_otel_trace_decision():
    tracer = OTelTracingAdapter()
    span_id = tracer.trace_decision(
        decision_type="allocation",
        confidence=0.85,
        regime="VOLATILE",
    )
    tracer.end_span(span_id)

    spans = tracer.get_spans_by_name("intelligence.")
    assert len(spans) == 1
    assert spans[0].attributes["dix.confidence"] == 0.85


def test_otel_trace_execution():
    tracer = OTelTracingAdapter()
    span_id = tracer.trace_execution(
        symbol="ETH/USDT",
        side="buy",
        amount=1.5,
        exchange="binance",
    )
    assert tracer.active_span_count == 1
    tracer.end_span(span_id)
    assert tracer.total_spans == 1


# --- OpenTelemetry Metrics Tests ---


def test_metrics_counter():
    metrics = OTelMetricsAdapter()
    metrics.increment("dix_orders_total", labels={"side": "buy"})
    metrics.increment("dix_orders_total", labels={"side": "buy"})
    metrics.increment("dix_orders_total", labels={"side": "sell"})

    assert metrics.get_counter("dix_orders_total", labels={"side": "buy"}) == 2.0
    assert metrics.get_counter("dix_orders_total", labels={"side": "sell"}) == 1.0


def test_metrics_gauge():
    metrics = OTelMetricsAdapter()
    metrics.set_portfolio_heat(0.7)
    metrics.set_equity(100000.0)

    assert metrics.get_gauge("dix_portfolio_heat") == 0.7
    assert metrics.get_gauge("dix_equity") == 100000.0


def test_metrics_histogram():
    metrics = OTelMetricsAdapter()
    for i in range(100):
        metrics.record_decision_latency(float(i))

    stats = metrics.get_histogram_stats("dix_decision_duration_ms")
    assert stats["min"] == 0.0
    assert stats["max"] == 99.0
    assert stats["avg"] == 49.5
    assert stats["p50"] == 50.0


def test_metrics_record_order():
    metrics = OTelMetricsAdapter()
    metrics.record_order(exchange="binance", side="buy", status="filled")
    metrics.record_order(exchange="binance", side="buy", status="filled")

    key_labels = {"exchange": "binance", "side": "buy", "status": "filled"}
    assert metrics.get_counter("dix_orders_total", labels=key_labels) == 2.0


# --- DuckDB Tests ---


def test_duckdb_inmemory_insert():
    db = DuckDBAnalyticsAdapter()
    db.connect()
    db.initialize_schema()

    db.insert(
        AnalyticsTable.TRADES,
        {
            "trade_id": "t1",
            "ts_ns": 1000,
            "symbol": "BTC",
            "side": "buy",
            "quantity": 0.5,
            "price": 50000.0,
            "pnl": 500.0,
        },
    )

    info = db.table_info(AnalyticsTable.TRADES)
    assert info is not None
    assert info.row_count == 1


def test_duckdb_inmemory_bulk():
    db = DuckDBAnalyticsAdapter()
    db.connect()
    db.initialize_schema()

    rows = [
        {
            "trade_id": f"t{i}",
            "ts_ns": i * 1000,
            "symbol": "ETH",
            "side": "buy",
            "quantity": 1.0,
            "price": 3000.0 + i,
        }
        for i in range(10)
    ]
    count = db.insert_many(AnalyticsTable.TRADES, rows)
    assert count == 10


# --- Temporal Tests ---


def test_temporal_start_workflow():
    adapter = TemporalWorkflowAdapter()
    adapter.connect()

    def mock_handler(data):
        return {"result": "success", "value": data.get("amount", 0) * 2}

    adapter.register_workflow(WorkflowType.STRATEGY_EXECUTION, mock_handler)

    wf_id = adapter.start_workflow(
        WorkflowType.STRATEGY_EXECUTION,
        input_data={"amount": 100},
    )
    assert adapter.get_status(wf_id) == WorkflowStatus.COMPLETED
    result = adapter.get_result(wf_id)
    assert result is not None
    assert result["value"] == 200


def test_temporal_workflow_failure():
    adapter = TemporalWorkflowAdapter()
    adapter.connect()

    def failing_handler(data):
        raise ValueError("simulated failure")

    adapter.register_workflow(WorkflowType.RISK_CHECK, failing_handler)

    wf_id = adapter.start_workflow(WorkflowType.RISK_CHECK)
    assert adapter.get_status(wf_id) == WorkflowStatus.FAILED


def test_temporal_list_workflows():
    adapter = TemporalWorkflowAdapter()
    adapter.connect()

    adapter.start_workflow(WorkflowType.STRATEGY_EXECUTION)
    adapter.start_workflow(WorkflowType.LEARNING_CYCLE)
    adapter.start_workflow(WorkflowType.STRATEGY_EXECUTION)

    all_wf = adapter.list_workflows()
    assert len(all_wf) == 3

    exec_only = adapter.list_workflows(workflow_type=WorkflowType.STRATEGY_EXECUTION)
    assert len(exec_only) == 2


# --- Feast Tests ---


def test_feast_materialize():
    adapter = FeastFeatureAdapter(use_inmemory=True)
    adapter.connect()

    count = adapter.materialize(
        "BTC/USDT",
        features={"sma_20": 50000.0, "rsi_14": 65.0, "volatility_20": 0.03},
        group=FeatureGroup.MARKET,
        ts_ns=1000,
    )
    assert count == 3
    assert adapter.feature_count() == 3


def test_feast_get_online_features():
    adapter = FeastFeatureAdapter(use_inmemory=True)
    adapter.connect()

    adapter.materialize(
        "ETH/USDT",
        features={"sma_20": 3000.0, "rsi_14": 45.0},
        group=FeatureGroup.MARKET,
    )

    vec = adapter.get_online_features("ETH/USDT", group=FeatureGroup.MARKET)
    assert vec is not None
    assert vec.features["sma_20"] == 3000.0
    assert vec.features["rsi_14"] == 45.0


def test_feast_filtered_features():
    adapter = FeastFeatureAdapter(use_inmemory=True)
    adapter.connect()

    adapter.materialize(
        "SOL/USDT",
        features={"sma_20": 150.0, "rsi_14": 70.0, "atr_14": 5.0},
        group=FeatureGroup.MARKET,
    )

    vec = adapter.get_online_features(
        "SOL/USDT",
        group=FeatureGroup.MARKET,
        feature_names=["rsi_14"],
    )
    assert vec is not None
    assert "rsi_14" in vec.features
    assert "sma_20" not in vec.features


def test_feast_registry():
    adapter = FeastFeatureAdapter(use_inmemory=True)
    registry = adapter.feature_registry
    assert len(registry) == len(FEATURE_REGISTRY)
    assert any(f.name == "sma_20" for f in registry)
    assert any(f.group == FeatureGroup.SENTIMENT for f in registry)


def test_feast_entity_count():
    adapter = FeastFeatureAdapter(use_inmemory=True)
    adapter.connect()

    adapter.materialize("BTC", features={"rsi_14": 50.0}, group=FeatureGroup.MARKET)
    adapter.materialize("ETH", features={"rsi_14": 60.0}, group=FeatureGroup.MARKET)
    adapter.materialize("trader_1", features={"win_rate": 0.6}, group=FeatureGroup.TRADER)

    assert adapter.entity_count(FeatureGroup.MARKET) == 2
    assert adapter.entity_count(FeatureGroup.TRADER) == 1
    assert adapter.entity_count() == 3
