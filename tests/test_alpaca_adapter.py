# ADAPTED FROM: alpacahq/alpaca-py (test patterns)
"""Tests for the Alpaca Markets adapter (I-17)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.contracts.events import ExecutionStatus, Side, SignalEvent
from execution_engine.adapters.alpaca import _ALPACA_STATUS, AlpacaAdapter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _signal(symbol: str = "AAPL", side: Side = Side.BUY, qty: float = 10.0) -> SignalEvent:
    return SignalEvent(
        ts_ns=1_000_000_000,
        symbol=symbol,
        side=side,
        confidence=0.9,
        meta={"qty": str(qty)},
        produced_by_engine="intelligence_engine",
    )


# ---------------------------------------------------------------------------
# Construction + lifecycle
# ---------------------------------------------------------------------------


def test_construction_defaults() -> None:
    adapter = AlpacaAdapter()
    assert adapter.name == "alpaca"
    assert adapter.venue == "alpaca:paper"
    assert adapter._paper is True


def test_construction_live() -> None:
    adapter = AlpacaAdapter(api_key="k", secret_key="s", paper=False)
    assert adapter.venue == "alpaca:live"
    assert adapter._base_url == "https://api.alpaca.markets"


def test_submit_rejects_when_not_connected() -> None:
    adapter = AlpacaAdapter()
    ev = adapter.submit(_signal(), mark_price=150.0)
    assert ev.status == ExecutionStatus.REJECTED
    assert ev.meta["reason"] == "adapter_not_ready"


def test_connect_without_credentials() -> None:
    adapter = AlpacaAdapter()
    adapter.connect()
    assert adapter._state.value == "DISCONNECTED"
    assert "credentials not wired" in adapter._detail


# ---------------------------------------------------------------------------
# Status mapping coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "alpaca_status,expected",
    [
        ("new", ExecutionStatus.FILLED),
        ("filled", ExecutionStatus.FILLED),
        ("partially_filled", ExecutionStatus.PARTIALLY_FILLED),
        ("canceled", ExecutionStatus.CANCELLED),
        ("rejected", ExecutionStatus.REJECTED),
        ("expired", ExecutionStatus.CANCELLED),
    ],
)
def test_status_mapping(alpaca_status: str, expected: ExecutionStatus) -> None:
    assert _ALPACA_STATUS[alpaca_status] == expected


# ---------------------------------------------------------------------------
# Submit with mocked HTTP
# ---------------------------------------------------------------------------


def test_submit_success_mocked() -> None:
    adapter = AlpacaAdapter(api_key="test_key", secret_key="test_secret")
    # Force READY state
    adapter._state = adapter._state.__class__("READY")

    mock_response = {
        "id": "order-123",
        "status": "filled",
        "filled_qty": "10",
        "filled_avg_price": "152.50",
        "symbol": "AAPL",
        "side": "buy",
        "type": "market",
        "client_order_id": "client-456",
    }

    with patch.object(adapter, "_request", return_value=mock_response):
        ev = adapter.submit(_signal("AAPL", Side.BUY, 10.0), mark_price=150.0)

    assert ev.status == ExecutionStatus.FILLED
    assert ev.qty == 10.0
    assert ev.price == 152.50
    assert ev.order_id == "order-123"
    assert ev.venue == "alpaca:paper"
    assert ev.meta["alpaca_status"] == "filled"


def test_submit_http_error_mocked() -> None:
    adapter = AlpacaAdapter(api_key="test_key", secret_key="test_secret")
    adapter._state = adapter._state.__class__("READY")

    import urllib.error

    error = urllib.error.HTTPError(
        url="https://paper-api.alpaca.markets/v2/orders",
        code=403,
        msg="Forbidden",
        hdrs={},  # type: ignore[arg-type]
        fp=None,
    )
    # HTTPError.read() needs to return bytes
    error.read = lambda: b'{"message": "insufficient buying power"}'  # type: ignore[assignment]

    with patch.object(adapter, "_request", side_effect=error):
        ev = adapter.submit(_signal(), mark_price=150.0)

    assert ev.status == ExecutionStatus.FAILED
    assert "insufficient buying power" in ev.meta["alpaca_error"]
    assert ev.meta["alpaca_http_status"] == "403"


# ---------------------------------------------------------------------------
# Symbol normalization
# ---------------------------------------------------------------------------


def test_symbol_slash_removed() -> None:
    adapter = AlpacaAdapter(api_key="k", secret_key="s")
    adapter._state = adapter._state.__class__("READY")

    captured = {}

    def mock_request(method: str, path: str, body: dict | None = None) -> dict:
        captured["body"] = body
        return {"id": "x", "status": "new", "filled_qty": "0", "filled_avg_price": None}

    with patch.object(adapter, "_request", side_effect=mock_request):
        adapter.submit(_signal("BTC/USD"), mark_price=50000.0)

    assert captured["body"]["symbol"] == "BTCUSD"


# ---------------------------------------------------------------------------
# Module-level contract
# ---------------------------------------------------------------------------


def test_module_exports() -> None:
    from execution_engine.adapters import alpaca

    assert hasattr(alpaca, "AlpacaAdapter")
    assert hasattr(alpaca, "__all__")
