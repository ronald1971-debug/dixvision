# ADAPTED FROM: erdewit/ib_insync (test patterns)
"""Tests for the Interactive Brokers adapter (I-18)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.contracts.events import ExecutionStatus, Side, SignalEvent
from execution_engine.adapters.ibkr import _IB_STATUS, IBKRAdapter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _signal(symbol: str = "AAPL", side: Side = Side.BUY, qty: float = 100.0) -> SignalEvent:
    return SignalEvent(
        ts_ns=2_000_000_000,
        symbol=symbol,
        side=side,
        confidence=0.85,
        meta={"qty": str(qty)},
        produced_by_engine="intelligence_engine",
    )


# ---------------------------------------------------------------------------
# Construction + lifecycle
# ---------------------------------------------------------------------------


def test_construction_defaults() -> None:
    adapter = IBKRAdapter()
    assert adapter.name == "ibkr"
    assert adapter.venue == "ibkr:paper"
    assert adapter._port == 7497
    assert adapter._paper is True


def test_construction_live() -> None:
    adapter = IBKRAdapter(paper=False)
    assert adapter.venue == "ibkr:live"
    assert adapter._port == 4001


def test_submit_rejects_when_not_connected() -> None:
    adapter = IBKRAdapter()
    ev = adapter.submit(_signal(), mark_price=150.0)
    assert ev.status == ExecutionStatus.REJECTED
    assert ev.meta["reason"] == "adapter_not_ready"


def test_connect_without_ib_insync() -> None:
    adapter = IBKRAdapter()
    with patch.dict("sys.modules", {"ib_insync": None}):
        # This will raise ImportError internally
        adapter.connect()
    # Should be DISCONNECTED or DEGRADED depending on error path
    assert adapter._state.value in ("DISCONNECTED", "DEGRADED")


# ---------------------------------------------------------------------------
# Status mapping coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ib_status,expected",
    [
        ("Submitted", ExecutionStatus.FILLED),
        ("Filled", ExecutionStatus.FILLED),
        ("Cancelled", ExecutionStatus.CANCELLED),
        ("Inactive", ExecutionStatus.REJECTED),
        ("PendingSubmit", ExecutionStatus.FILLED),
        ("ApiCancelled", ExecutionStatus.CANCELLED),
    ],
)
def test_status_mapping(ib_status: str, expected: ExecutionStatus) -> None:
    assert _IB_STATUS[ib_status] == expected


# ---------------------------------------------------------------------------
# Contract building
# ---------------------------------------------------------------------------


def test_build_contract_stock() -> None:
    adapter = IBKRAdapter()
    ib_mock = MagicMock()
    contract = adapter._build_contract("AAPL", ib_mock)
    ib_mock.Stock.assert_called_once_with(symbol="AAPL", exchange="SMART", currency="USD")
    assert contract == ib_mock.Stock.return_value


def test_build_contract_forex() -> None:
    adapter = IBKRAdapter()
    ib_mock = MagicMock()
    adapter._build_contract("EUR/USD", ib_mock)
    ib_mock.Forex.assert_called_once_with("EURUSD")


def test_build_contract_future() -> None:
    adapter = IBKRAdapter()
    ib_mock = MagicMock()
    adapter._build_contract("ES202506", ib_mock)
    ib_mock.Future.assert_called_once_with(
        symbol="ES",
        lastTradeDateOrContractMonth="202506",
        exchange="CME",
    )


# ---------------------------------------------------------------------------
# Submit with mocked ib_insync
# ---------------------------------------------------------------------------


def test_submit_success_mocked() -> None:
    adapter = IBKRAdapter()
    adapter._state = adapter._state.__class__("READY")

    # Mock the ib_insync module and IB instance
    mock_ib = MagicMock()
    adapter._ib = mock_ib

    # Build mock trade response (mirrors ib_insync Trade object)
    mock_trade = MagicMock()
    mock_trade.orderStatus.status = "Filled"
    mock_trade.orderStatus.filled = 100.0
    mock_trade.orderStatus.avgFillPrice = 151.25
    mock_trade.order.orderId = 42
    mock_trade.order.permId = 99999
    mock_ib.placeOrder.return_value = mock_trade

    with patch.dict("sys.modules", {"ib_insync": MagicMock()}):
        ev = adapter._submit_live(_signal("AAPL", Side.BUY, 100.0), mark_price=150.0)

    assert ev.status == ExecutionStatus.FILLED
    assert ev.qty == 100.0
    assert ev.price == 151.25
    assert ev.order_id == "42"
    assert ev.venue == "ibkr:paper"


def test_submit_exception_returns_failed() -> None:
    adapter = IBKRAdapter()
    adapter._state = adapter._state.__class__("READY")
    adapter._ib = MagicMock()
    adapter._ib.placeOrder.side_effect = ConnectionError("TWS not running")

    with patch.dict("sys.modules", {"ib_insync": MagicMock()}):
        ev = adapter._submit_live(_signal(), mark_price=150.0)

    assert ev.status == ExecutionStatus.FAILED
    assert "TWS not running" in ev.meta["ib_error"]


# ---------------------------------------------------------------------------
# Module-level contract
# ---------------------------------------------------------------------------


def test_module_exports() -> None:
    from execution_engine.adapters import ibkr

    assert hasattr(ibkr, "IBKRAdapter")
    assert hasattr(ibkr, "__all__")
