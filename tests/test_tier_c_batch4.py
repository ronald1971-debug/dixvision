"""Tests for Tier C batch 4: C-86..C-91 (visualization, reference architectures)."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# C-86: Graph visualizer
# ---------------------------------------------------------------------------


def test_graph_visualizer_add_nodes_edges() -> None:
    from tools.graph_visualizer import GraphVisualizer

    viz = GraphVisualizer(in_memory=True)
    viz.add_node("A", label="Strategy Alpha", group="cluster-1")
    viz.add_node("B", label="Strategy Beta", group="cluster-1")
    viz.add_node("C", label="Strategy Gamma", group="cluster-2")
    viz.add_edge("A", "B", weight=0.9)
    viz.add_edge("B", "C", weight=0.5)

    assert viz.node_count == 3
    assert viz.edge_count == 2


def test_graph_visualizer_community_detection() -> None:
    from tools.graph_visualizer import GraphVisualizer

    viz = GraphVisualizer(in_memory=True)
    viz.add_node("A")
    viz.add_node("B")
    viz.add_node("C")
    viz.add_edge("A", "B")
    # C is disconnected
    communities = viz.detect_communities()
    assert communities["A"] == communities["B"]
    assert communities["C"] != communities["A"]


def test_graph_visualizer_render_html() -> None:
    from tools.graph_visualizer import GraphVisualizer

    viz = GraphVisualizer(title="Test Graph", in_memory=True)
    viz.add_node("X", label="Node X")
    html = viz.render_html()
    assert "<html>" in html
    assert "Test Graph" in html


def test_graph_visualizer_to_dict() -> None:
    from tools.graph_visualizer import GraphVisualizer

    viz = GraphVisualizer(in_memory=True)
    viz.add_node("A", label="A")
    viz.add_edge("A", "A", weight=1.0)
    data = viz.get_graph_data().to_dict()
    assert len(data["nodes"]) == 1
    assert len(data["edges"]) == 1


# ---------------------------------------------------------------------------
# C-87: Operator terminal
# ---------------------------------------------------------------------------


def test_operator_terminal_mock_refresh() -> None:
    from tools.operator_terminal import OperatorTerminal

    terminal = OperatorTerminal(in_memory=True)
    terminal.add_mock_position({"symbol": "AAPL", "qty": 100})
    terminal.add_mock_event({"level": "WARNING", "message": "Vol spike"})

    state = terminal.refresh()
    assert state.governance_mode == "SAFE"
    assert len(state.positions) == 1
    assert state.positions[0]["symbol"] == "AAPL"
    assert len(state.hazard_events) == 1


# ---------------------------------------------------------------------------
# C-88: CLI dashboard
# ---------------------------------------------------------------------------


def test_cli_dashboard_poll_and_render() -> None:
    from tools.cli_dashboard import CLIDashboard, DashboardSnapshot

    dash = CLIDashboard(in_memory=True)
    dash.set_mock_data(
        DashboardSnapshot(
            positions=[{"symbol": "GOOG", "qty": 50}],
            recent_events=[{"level": "INFO", "message": "All clear"}],
            governance_mode="LIVE",
            uptime_seconds=3600.0,
        )
    )

    snapshot = dash.poll()
    assert snapshot.governance_mode == "LIVE"
    assert len(dash.history) == 1

    text = dash.render_text(snapshot)
    assert "LIVE" in text
    assert "GOOG" in text


# ---------------------------------------------------------------------------
# C-89: Analytics charts
# ---------------------------------------------------------------------------


def test_analytics_charts_pnl_curve() -> None:
    from learning_engine.analytics.charts import AnalyticsCharts

    charts = AnalyticsCharts(in_memory=True)
    spec = charts.pnl_curve(
        dates=["2024-01-01", "2024-01-02", "2024-01-03"],
        cumulative_returns=[0.0, 0.02, 0.05],
        title="Test PnL",
    )
    assert spec.title == "Test PnL"
    assert len(spec.traces) == 1
    assert spec.traces[0].name == "PnL"


def test_analytics_charts_render_html() -> None:
    from learning_engine.analytics.charts import AnalyticsCharts

    charts = AnalyticsCharts(in_memory=True)
    spec = charts.drawdown_chart(
        dates=["D1", "D2"],
        drawdowns=[-0.01, -0.03],
    )
    html = charts.render_html(spec)
    assert "<html>" in html
    assert "Drawdown" in html


def test_analytics_charts_feature_importance() -> None:
    from learning_engine.analytics.charts import AnalyticsCharts

    charts = AnalyticsCharts(in_memory=True)
    spec = charts.feature_importance(
        feature_names=["vol", "momentum", "rsi"],
        importances=[0.4, 0.35, 0.25],
    )
    assert spec.traces[0].trace_type == "bar"
    data = spec.to_dict()
    assert data["data"][0]["type"] == "bar"


# ---------------------------------------------------------------------------
# C-91: vnpy bridge
# ---------------------------------------------------------------------------


def test_vnpy_bridge_connect_and_order() -> None:
    from execution_engine.adapters.vnpy_bridge import (
        VnpyBridge,
        VnpyOrderRequest,
    )

    bridge = VnpyBridge(exchange="BINANCE", in_memory=True)
    assert bridge.connect() is True
    assert bridge.is_connected is True

    request = VnpyOrderRequest(
        symbol="BTCUSDT",
        exchange="BINANCE",
        direction="BUY",
        order_type="LIMIT",
        volume=0.1,
        price=50000.0,
    )
    result = bridge.send_order(request)
    assert result.status == "FILLED"
    assert result.order_id.startswith("vnpy-")
    assert result.filled_volume == 0.1
    assert len(bridge.order_history) == 1


def test_vnpy_bridge_rejected_when_disconnected() -> None:
    from execution_engine.adapters.vnpy_bridge import (
        VnpyBridge,
        VnpyOrderRequest,
    )

    bridge = VnpyBridge(exchange="OKX", in_memory=True)
    # Don't connect
    request = VnpyOrderRequest(
        symbol="ETHUSDT",
        exchange="OKX",
        direction="SELL",
        order_type="MARKET",
        volume=1.0,
    )
    result = bridge.send_order(request)
    assert result.status == "REJECTED"
