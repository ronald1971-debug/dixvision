"""Tests for OSS integration adapters."""

from integrations.ccxt_adapter.exchange import (
    CCXTExchangeAdapter,
    ExchangeId,
    OrderSide,
    OrderType,
)
from integrations.langgraph_adapter.orchestrator import (
    AgentMessage,
    AgentRole,
    GraphConfig,
    GraphState,
    LangGraphOrchestrator,
)
from integrations.opa_adapter.policy import (
    OPAPolicyAdapter,
    PolicyDecision,
    PolicyDomain,
    PolicyInput,
)
from integrations.qdrant_adapter.memory import (
    MemoryDomain,
    QdrantMemoryAdapter,
    VectorPoint,
)

# --- CCXT Adapter Tests ---


def test_ccxt_adapter_init():
    adapter = CCXTExchangeAdapter(
        exchange_id=ExchangeId.BINANCE,
        sandbox=True,
        execution_enabled=False,
    )
    assert adapter.exchange_id == ExchangeId.BINANCE
    assert not adapter.execution_enabled
    assert not adapter.is_connected


def test_ccxt_adapter_kill_switch():
    adapter = CCXTExchangeAdapter(
        exchange_id=ExchangeId.BINANCE,
        execution_enabled=True,
    )
    assert adapter.execution_enabled

    adapter.activate_kill_switch()
    assert not adapter.execution_enabled

    adapter.deactivate_kill_switch()
    assert adapter.execution_enabled


def test_ccxt_adapter_execution_gated():
    adapter = CCXTExchangeAdapter(
        exchange_id=ExchangeId.BINANCE,
        execution_enabled=False,
    )
    # Should return None when execution disabled
    result = adapter.create_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        amount=0.01,
    )
    assert result is None


def test_ccxt_adapter_no_connection_returns_empty():
    adapter = CCXTExchangeAdapter(exchange_id=ExchangeId.BINANCE)
    assert adapter.fetch_ticker("BTC/USDT") is None
    assert adapter.fetch_ohlcv("BTC/USDT") == []
    assert adapter.fetch_balance() == []


# --- Qdrant Adapter Tests ---


def test_qdrant_inmemory_upsert():
    adapter = QdrantMemoryAdapter(use_inmemory=True)
    adapter.connect()
    adapter.create_collection(MemoryDomain.TRADERS)

    points = [
        VectorPoint(
            point_id="trader_soros",
            vector=(0.1, 0.2, 0.3, 0.4),
            payload={"name": "Soros", "style": "macro"},
        ),
        VectorPoint(
            point_id="trader_simons",
            vector=(0.9, 0.8, 0.7, 0.6),
            payload={"name": "Simons", "style": "quant"},
        ),
    ]
    count = adapter.upsert(MemoryDomain.TRADERS, points=points)
    assert count == 2
    assert adapter.count(MemoryDomain.TRADERS) == 2


def test_qdrant_inmemory_search():
    adapter = QdrantMemoryAdapter(use_inmemory=True, vector_size=4)
    adapter.connect()
    adapter.create_collection(MemoryDomain.STRATEGIES)

    adapter.upsert(
        MemoryDomain.STRATEGIES,
        points=[
            VectorPoint("strat_1", (1.0, 0.0, 0.0, 0.0), {"name": "trend"}),
            VectorPoint("strat_2", (0.0, 1.0, 0.0, 0.0), {"name": "mean_rev"}),
            VectorPoint("strat_3", (0.9, 0.1, 0.0, 0.0), {"name": "momentum"}),
        ],
    )

    # Search for something similar to strat_1
    results = adapter.search(
        MemoryDomain.STRATEGIES,
        query_vector=(0.95, 0.05, 0.0, 0.0),
        limit=2,
    )
    assert len(results) == 2
    # Most similar should be strat_3 or strat_1
    assert results[0].point_id in ("strat_1", "strat_3")


def test_qdrant_inmemory_delete():
    adapter = QdrantMemoryAdapter(use_inmemory=True)
    adapter.connect()
    adapter.create_collection(MemoryDomain.NARRATIVES)

    adapter.upsert(
        MemoryDomain.NARRATIVES,
        points=[
            VectorPoint("n1", (0.1, 0.2), {"theme": "risk_on"}),
            VectorPoint("n2", (0.3, 0.4), {"theme": "risk_off"}),
        ],
    )
    assert adapter.count(MemoryDomain.NARRATIVES) == 2

    deleted = adapter.delete(MemoryDomain.NARRATIVES, point_ids=["n1"])
    assert deleted == 1
    assert adapter.count(MemoryDomain.NARRATIVES) == 1


def test_qdrant_collection_info():
    adapter = QdrantMemoryAdapter(use_inmemory=True, vector_size=128)
    adapter.connect()
    adapter.create_collection(MemoryDomain.REGIMES)

    info = adapter.collection_info(MemoryDomain.REGIMES)
    assert info is not None
    assert info.name == "dix_regimes"
    assert info.vector_size == 128
    assert info.point_count == 0


# --- LangGraph Adapter Tests ---


def test_langgraph_register_agents():
    orchestrator = LangGraphOrchestrator()

    def mock_planner(data, ctx):
        return AgentMessage(
            sender=AgentRole.PLANNER,
            content="Plan: buy BTC",
            confidence=0.8,
        )

    orchestrator.register_agent(AgentRole.PLANNER, mock_planner)
    assert orchestrator.state == GraphState.IDLE


def test_langgraph_execute_simple():
    orchestrator = LangGraphOrchestrator(config=GraphConfig(governance_required=False))

    def mock_planner(data, ctx):
        return AgentMessage(
            sender=AgentRole.PLANNER,
            content="Plan ready",
            confidence=0.9,
        )

    def mock_executor(data, ctx):
        return AgentMessage(
            sender=AgentRole.EXECUTOR,
            content="Executed",
            confidence=1.0,
        )

    orchestrator.register_agent(AgentRole.PLANNER, mock_planner)
    orchestrator.register_agent(AgentRole.EXECUTOR, mock_executor)

    result = orchestrator.execute(input_data={"action": "trade"})
    assert result.state == GraphState.COMPLETE
    assert len(result.messages) >= 1


def test_langgraph_governance_gate():
    orchestrator = LangGraphOrchestrator(config=GraphConfig(governance_required=True))

    def mock_governor(data, ctx):
        # Governor does NOT approve
        ctx.governance_approved = False
        return AgentMessage(
            sender=AgentRole.GOVERNOR,
            content="Denied",
            confidence=1.0,
        )

    orchestrator.register_agent(AgentRole.GOVERNOR, mock_governor)

    result = orchestrator.execute(input_data={"action": "trade"})
    assert result.state == GraphState.GOVERNANCE_GATE


# --- OPA Adapter Tests ---


def test_opa_execution_allow():
    opa = OPAPolicyAdapter(use_builtin=True)
    opa.connect()

    result = opa.evaluate_execution(
        kill_switch=False,
        mode="PAPER",
        operator_approved=True,
    )
    assert result.decision == PolicyDecision.ALLOW
    assert result.reasons == ()


def test_opa_execution_deny_kill_switch():
    opa = OPAPolicyAdapter(use_builtin=True)
    opa.connect()

    result = opa.evaluate_execution(
        kill_switch=True,
        mode="PAPER",
        operator_approved=True,
    )
    assert result.decision == PolicyDecision.DENY
    assert "kill_switch_active" in result.reasons


def test_opa_execution_deny_locked():
    opa = OPAPolicyAdapter(use_builtin=True)
    opa.connect()

    result = opa.evaluate_execution(
        kill_switch=False,
        mode="LOCKED",
        operator_approved=True,
    )
    assert result.decision == PolicyDecision.DENY
    assert "mode_locked" in result.reasons


def test_opa_risk_allow():
    opa = OPAPolicyAdapter(use_builtin=True)
    result = opa.evaluate_risk(
        position_size=0.5,
        max_position_size=1.0,
        portfolio_heat=0.3,
        max_heat=0.5,
        drawdown=0.05,
        max_drawdown=0.10,
    )
    assert result.decision == PolicyDecision.ALLOW


def test_opa_risk_deny_position():
    opa = OPAPolicyAdapter(use_builtin=True)
    result = opa.evaluate_risk(
        position_size=2.0,
        max_position_size=1.0,
        portfolio_heat=0.3,
        max_heat=0.5,
        drawdown=0.05,
        max_drawdown=0.10,
    )
    assert result.decision == PolicyDecision.DENY
    assert "position_too_large" in result.reasons


def test_opa_mode_transition():
    opa = OPAPolicyAdapter(use_builtin=True)

    # Valid: SAFE → PAPER
    result = opa.evaluate(
        PolicyInput(
            domain=PolicyDomain.MODE_TRANSITION,
            action="transition",
            subject="operator",
            resource="mode",
            context={
                "from_mode": "SAFE",
                "to_mode": "PAPER",
                "operator_authorized": True,
            },
        )
    )
    assert result.decision == PolicyDecision.ALLOW

    # Invalid: SAFE → LIVE (must go through PAPER → CANARY first)
    result = opa.evaluate(
        PolicyInput(
            domain=PolicyDomain.MODE_TRANSITION,
            action="transition",
            subject="operator",
            resource="mode",
            context={
                "from_mode": "SAFE",
                "to_mode": "LIVE",
                "operator_authorized": True,
            },
        )
    )
    assert result.decision == PolicyDecision.DENY


def test_opa_decision_log():
    opa = OPAPolicyAdapter(use_builtin=True)
    opa.evaluate_execution(kill_switch=False, mode="PAPER", operator_approved=True)
    opa.evaluate_execution(kill_switch=True, mode="PAPER", operator_approved=True)

    assert opa.decision_count == 2
    recent = opa.recent_decisions
    assert len(recent) == 2
    assert recent[0].decision == PolicyDecision.ALLOW
    assert recent[1].decision == PolicyDecision.DENY
