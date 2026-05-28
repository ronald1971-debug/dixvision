"""Tests for OSS integration wiring — bridges connecting adapters to engines."""

from integrations.wiring.ccxt_execution_bridge import (
    CCXTExecutionBridge,
)
from integrations.wiring.kafka_event_bridge import (
    KafkaEventBridge,
)
from integrations.wiring.opa_governance_bridge import (
    OPAGovernanceBridge,
)
from integrations.wiring.qdrant_memory_bridge import (
    QdrantMemoryBridge,
)

# --- CCXT Execution Bridge Tests ---


def test_ccxt_bridge_connect():
    bridge = CCXTExecutionBridge(sandbox=True)
    assert bridge.connect() is True
    assert bridge.is_connected is True


def test_ccxt_bridge_kill_switch_blocks_execution():
    bridge = CCXTExecutionBridge(sandbox=True)
    bridge.connect()
    bridge.enable_execution()
    bridge.activate_kill_switch()

    result = bridge.execute_order("BTC/USDT", "BUY", 0.01, operator_approved=True)
    assert result.success is False
    assert "kill switch" in result.error.lower()


def test_ccxt_bridge_no_approval_blocks_execution():
    bridge = CCXTExecutionBridge(sandbox=True)
    bridge.connect()
    bridge.enable_execution()

    result = bridge.execute_order("BTC/USDT", "BUY", 0.01, operator_approved=False)
    assert result.success is False
    assert "approval" in result.error.lower()


def test_ccxt_bridge_execution_not_enabled():
    bridge = CCXTExecutionBridge(sandbox=True)
    bridge.connect()

    result = bridge.execute_order("ETH/USDT", "SELL", 1.0, operator_approved=True)
    assert result.success is False
    assert "not enabled" in result.error.lower()


def test_ccxt_bridge_order_metrics():
    bridge = CCXTExecutionBridge(sandbox=True)
    bridge.connect()
    assert bridge.order_count == 0
    assert bridge.total_fees_usd == 0.0


# --- Qdrant Memory Bridge Tests ---


def test_qdrant_bridge_initialize():
    bridge = QdrantMemoryBridge(dimension=8)
    assert bridge.initialize() is True


def test_qdrant_bridge_store_narrative():
    bridge = QdrantMemoryBridge(dimension=4)
    bridge.initialize()

    result = bridge.store_narrative(
        "narrative_001",
        (0.1, 0.2, 0.3, 0.4),
        theme="BTC halving supercycle",
        strength=0.85,
    )
    assert result is True
    assert bridge.total_embeddings > 0


def test_qdrant_bridge_store_strategy():
    bridge = QdrantMemoryBridge(dimension=4)
    bridge.initialize()

    result = bridge.store_strategy(
        "strat_001",
        (0.5, 0.6, 0.7, 0.8),
        trader_base="Soros",
        win_rate=0.62,
        sharpe=1.8,
    )
    assert result is True


def test_qdrant_bridge_search():
    bridge = QdrantMemoryBridge(dimension=4)
    bridge.initialize()

    bridge.store_narrative("n1", (1.0, 0.0, 0.0, 0.0), theme="risk-off")
    bridge.store_narrative("n2", (0.0, 1.0, 0.0, 0.0), theme="risk-on")
    bridge.store_narrative("n3", (0.9, 0.1, 0.0, 0.0), theme="flight-to-safety")

    results = bridge.find_similar_narratives((1.0, 0.0, 0.0, 0.0), limit=2, min_score=0.5)
    assert len(results) > 0
    assert results[0].payload["theme"] in ("risk-off", "flight-to-safety")


def test_qdrant_bridge_store_regime():
    bridge = QdrantMemoryBridge(dimension=4)
    bridge.initialize()

    result = bridge.store_regime(
        "regime_001",
        (0.2, 0.3, 0.8, 0.1),
        regime_type="trending_bullish",
        confidence=0.92,
    )
    assert result is True


def test_qdrant_bridge_store_trader():
    bridge = QdrantMemoryBridge(dimension=4)
    bridge.initialize()

    result = bridge.store_trader(
        "trader_001",
        (0.4, 0.5, 0.6, 0.7),
        archetype="MACRO_SOROS_HIGH_RISK",
        group="A",
    )
    assert result is True
    assert bridge.insert_count > 0


# --- OPA Governance Bridge Tests ---


def test_opa_bridge_can_execute_kill_switch():
    bridge = OPAGovernanceBridge()
    bridge.initialize()

    verdict = bridge.can_execute(kill_switch=True, operator_approved=True)
    assert verdict.allowed is False
    assert "kill" in " ".join(verdict.reasons).lower()


def test_opa_bridge_can_execute_approved():
    bridge = OPAGovernanceBridge()
    bridge.initialize()

    verdict = bridge.can_execute(kill_switch=False, mode="PAPER", operator_approved=True)
    assert verdict.allowed is True


def test_opa_bridge_risk_within_limits():
    bridge = OPAGovernanceBridge()
    bridge.initialize()

    verdict = bridge.check_risk_limits(
        position_size=10.0,
        max_position_size=100.0,
        portfolio_heat=0.3,
        max_heat=0.6,
        drawdown=0.05,
        max_drawdown=0.15,
    )
    assert verdict.allowed is True


def test_opa_bridge_risk_exceeds_limits():
    bridge = OPAGovernanceBridge()
    bridge.initialize()

    verdict = bridge.check_risk_limits(
        position_size=150.0,
        max_position_size=100.0,
        portfolio_heat=0.8,
        max_heat=0.6,
        drawdown=0.20,
        max_drawdown=0.15,
    )
    assert verdict.allowed is False


def test_opa_bridge_metrics():
    bridge = OPAGovernanceBridge()
    bridge.initialize()

    bridge.can_execute(kill_switch=False, mode="PAPER", operator_approved=True)
    bridge.can_execute(kill_switch=True, mode="PAPER", operator_approved=True)

    assert bridge.evaluation_count == 2
    assert bridge.allow_rate > 0
    assert bridge.deny_rate > 0


# --- Kafka Event Bridge Tests ---


def test_kafka_bridge_initialize():
    bridge = KafkaEventBridge()
    assert bridge.initialize() is True
    assert bridge.is_connected is True


def test_kafka_bridge_publish_market_tick():
    bridge = KafkaEventBridge()
    bridge.initialize()

    envelope = bridge.publish_market_tick("BTC/USDT", price=67500.0, volume=1234.5)
    assert envelope.event_type == "market.tick"
    assert envelope.payload["price"] == 67500.0
    assert envelope.ts_ns > 0


def test_kafka_bridge_publish_signal():
    bridge = KafkaEventBridge()
    bridge.initialize()

    envelope = bridge.publish_signal(
        signal_id="sig_001",
        symbol="ETH/USDT",
        direction="BUY",
        confidence=0.85,
    )
    assert envelope.event_type == "signal.generated"
    assert envelope.payload["confidence"] == 0.85


def test_kafka_bridge_publish_governance():
    bridge = KafkaEventBridge()
    bridge.initialize()

    envelope = bridge.publish_governance_event(
        decision_type="mode_transition",
        decision="ALLOW",
        reason="operator approved",
    )
    assert envelope.event_type == "governance.decision"
    assert envelope.payload["decision"] == "ALLOW"


def test_kafka_bridge_publish_execution():
    bridge = KafkaEventBridge()
    bridge.initialize()

    envelope = bridge.publish_execution_event(
        order_id="ord_001",
        symbol="BTC/USDT",
        side="BUY",
        status="FILLED",
        filled=0.01,
        price=67500.0,
    )
    assert envelope.event_type == "execution.update"
    assert envelope.payload["status"] == "FILLED"


def test_kafka_bridge_metrics():
    bridge = KafkaEventBridge()
    bridge.initialize()

    bridge.publish_market_tick("BTC/USDT", price=67500.0)
    bridge.publish_signal(signal_id="s1", symbol="ETH/USDT", direction="BUY", confidence=0.9)

    assert bridge.published_count == 2
