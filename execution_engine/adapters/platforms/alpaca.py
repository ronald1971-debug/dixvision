"""Alpaca platform integration (Paper-S7).

Read-only adapter for Alpaca Markets: account, positions,
market data, and paper trading state monitoring.

Uses the Alpaca REST v2 API (paper-api or live-api) via stdlib urllib.
No external dependencies — credentials are passed explicitly (INV-65).

__capability_tier__ = 0
__forbidden_tiers__ = (5,)
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

__capability_tier__ = 0
__forbidden_tiers__ = (5,)

logger = logging.getLogger(__name__)

_PAPER_BASE = "https://paper-api.alpaca.markets"
_LIVE_BASE = "https://api.alpaca.markets"
_DATA_BASE = "https://data.alpaca.markets"


@dataclass(frozen=True, slots=True)
class AlpacaPosition:
    """An Alpaca position."""

    asset_id: str
    symbol: str
    side: str  # "long" | "short"
    qty: float
    avg_entry_price: float
    market_value: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    change_today: float


@dataclass(frozen=True, slots=True)
class AlpacaAccount:
    """Alpaca account info."""

    account_id: str
    status: str  # "ACTIVE" | "INACTIVE"
    equity: float
    cash: float
    buying_power: float
    portfolio_value: float
    pattern_day_trader: bool
    trading_blocked: bool
    account_blocked: bool
    daytrade_count: int
    currency: str


@dataclass(frozen=True, slots=True)
class AlpacaBar:
    """Alpaca OHLCV bar."""

    symbol: str
    ts_ns: int
    open_price: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float
    trade_count: int


class AlpacaAdapter:
    """Read-only adapter for Alpaca Markets.

    Reads account state, positions, and market data via the Alpaca REST v2 API.
    Supports both live and paper trading accounts.
    Never places orders — use execution_engine.adapters.alpaca.AlpacaAdapter for that.

    Args:
        api_key: Alpaca API key ID. Empty string = scaffold mode (returns empty data).
        api_secret: Alpaca secret key. Empty string = scaffold mode.
        paper: Route to paper-api.alpaca.markets when True (default).
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        api_secret: str = "",
        paper: bool = True,
    ) -> None:
        self._key = api_key
        self._secret = api_secret
        self._paper = paper
        self._base_url = _PAPER_BASE if paper else _LIVE_BASE
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Verify credentials by fetching /v2/account.

        Returns:
            True if credentials are valid and connection succeeded.
        """
        if not self._key or not self._secret:
            logger.warning("AlpacaAdapter (platforms): no credentials — scaffold mode")
            return False
        try:
            self._request("GET", "/v2/account")
            self._connected = True
            logger.info("AlpacaAdapter (platforms): connected paper=%s", self._paper)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("AlpacaAdapter (platforms): connect failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Account & positions
    # ------------------------------------------------------------------

    def fetch_account(self) -> AlpacaAccount | None:
        """Fetch account info from /v2/account."""
        if not self._key:
            return None
        try:
            data = self._request("GET", "/v2/account")
            return AlpacaAccount(
                account_id=str(data.get("id", "")),
                status=str(data.get("status", "INACTIVE")),
                equity=float(data.get("equity", 0.0) or 0.0),
                cash=float(data.get("cash", 0.0) or 0.0),
                buying_power=float(data.get("buying_power", 0.0) or 0.0),
                portfolio_value=float(data.get("portfolio_value", 0.0) or 0.0),
                pattern_day_trader=bool(data.get("pattern_day_trader", False)),
                trading_blocked=bool(data.get("trading_blocked", False)),
                account_blocked=bool(data.get("account_blocked", False)),
                daytrade_count=int(data.get("daytrade_count", 0) or 0),
                currency=str(data.get("currency", "USD")),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("AlpacaAdapter.fetch_account: %s", exc)
            return None

    def fetch_positions(self) -> list[AlpacaPosition]:
        """Fetch all open positions from /v2/positions."""
        if not self._key:
            return []
        try:
            data = self._request("GET", "/v2/positions")
            if not isinstance(data, list):
                return []
            positions: list[AlpacaPosition] = []
            for p in data:
                positions.append(AlpacaPosition(
                    asset_id=str(p.get("asset_id", "")),
                    symbol=str(p.get("symbol", "")),
                    side=str(p.get("side", "long")),
                    qty=float(p.get("qty", 0.0) or 0.0),
                    avg_entry_price=float(p.get("avg_entry_price", 0.0) or 0.0),
                    market_value=float(p.get("market_value", 0.0) or 0.0),
                    current_price=float(p.get("current_price", 0.0) or 0.0),
                    unrealized_pnl=float(p.get("unrealized_pl", 0.0) or 0.0),
                    unrealized_pnl_pct=float(p.get("unrealized_plpc", 0.0) or 0.0),
                    change_today=float(p.get("change_today", 0.0) or 0.0),
                ))
            return positions
        except Exception as exc:  # noqa: BLE001
            logger.error("AlpacaAdapter.fetch_positions: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def fetch_bars(
        self,
        *,
        symbol: str,
        timeframe: str = "1Day",
        limit: int = 100,
    ) -> list[AlpacaBar]:
        """Fetch historical OHLCV bars from Alpaca Data API.

        Args:
            symbol: Equity symbol (e.g. ``"AAPL"``).
            timeframe: Alpaca timeframe string (``"1Min"``, ``"1Hour"``, ``"1Day"``).
            limit: Max bars to return.

        Returns:
            List of :class:`AlpacaBar` sorted by time ascending.
        """
        if not self._key:
            return []
        try:
            import urllib.parse
            params = urllib.parse.urlencode({
                "timeframe": timeframe,
                "limit": str(limit),
                "adjustment": "raw",
            })
            path = f"/v2/stocks/{urllib.parse.quote(symbol)}/bars?{params}"
            data = self._data_request("GET", path)
            raw_bars = data.get("bars", []) if isinstance(data, dict) else []
            bars: list[AlpacaBar] = []
            for b in raw_bars:
                # Alpaca returns RFC3339 timestamps; convert to ns via simple parse.
                ts_ns = _alpaca_ts_to_ns(str(b.get("t", "")))
                bars.append(AlpacaBar(
                    symbol=symbol,
                    ts_ns=ts_ns,
                    open_price=float(b.get("o", 0.0) or 0.0),
                    high=float(b.get("h", 0.0) or 0.0),
                    low=float(b.get("l", 0.0) or 0.0),
                    close=float(b.get("c", 0.0) or 0.0),
                    volume=int(b.get("v", 0) or 0),
                    vwap=float(b.get("vw", 0.0) or 0.0),
                    trade_count=int(b.get("n", 0) or 0),
                ))
            return bars
        except Exception as exc:  # noqa: BLE001
            logger.error("AlpacaAdapter.fetch_bars: symbol=%s error=%s", symbol, exc)
            return []

    def fetch_latest_quote(self, *, symbol: str) -> dict[str, Any]:
        """Fetch latest NBBO quote for a symbol.

        Returns:
            Dict with keys ``ask``, ``bid``, ``ask_size``, ``bid_size``, ``ts_ns``.
        """
        if not self._key:
            return {}
        try:
            import urllib.parse
            path = f"/v2/stocks/{urllib.parse.quote(symbol)}/quotes/latest"
            data = self._data_request("GET", path)
            q = data.get("quote", {}) if isinstance(data, dict) else {}
            return {
                "ask": float(q.get("ap", 0.0) or 0.0),
                "bid": float(q.get("bp", 0.0) or 0.0),
                "ask_size": int(q.get("as", 0) or 0),
                "bid_size": int(q.get("bs", 0) or 0),
                "ts_ns": _alpaca_ts_to_ns(str(q.get("t", ""))),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("AlpacaAdapter.fetch_latest_quote: symbol=%s error=%s", symbol, exc)
            return {}

    def fetch_order_history(
        self,
        *,
        status: str = "all",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch order history from /v2/orders (monitoring only).

        Args:
            status: Alpaca order status filter (``"all"``, ``"open"``, ``"closed"``).
            limit: Max orders to return.
        """
        if not self._key:
            return []
        try:
            import urllib.parse
            params = urllib.parse.urlencode({"status": status, "limit": str(limit)})
            data = self._request("GET", f"/v2/orders?{params}")
            if not isinstance(data, list):
                return []
            return [
                {
                    "id": str(o.get("id", "")),
                    "symbol": str(o.get("symbol", "")),
                    "side": str(o.get("side", "")),
                    "type": str(o.get("type", "")),
                    "status": str(o.get("status", "")),
                    "qty": float(o.get("qty", 0.0) or 0.0),
                    "filled_qty": float(o.get("filled_qty", 0.0) or 0.0),
                    "filled_avg_price": float(o.get("filled_avg_price", 0.0) or 0.0),
                    "submitted_at": str(o.get("submitted_at", "")),
                    "filled_at": str(o.get("filled_at", "") or ""),
                }
                for o in data
            ]
        except Exception as exc:  # noqa: BLE001
            logger.error("AlpacaAdapter.fetch_order_history: %s", exc)
            return []

    def fetch_portfolio_history(
        self,
        *,
        period: str = "1M",
        timeframe: str = "1D",
    ) -> dict[str, Any]:
        """Fetch portfolio performance history from /v2/account/portfolio/history.

        Returns:
            Dict with ``timestamps``, ``equity``, ``profit_loss``, ``profit_loss_pct``.
        """
        if not self._key:
            return {}
        try:
            import urllib.parse
            params = urllib.parse.urlencode({"period": period, "timeframe": timeframe})
            data = self._request("GET", f"/v2/account/portfolio/history?{params}")
            if not isinstance(data, dict):
                return {}
            return {
                "timestamps": data.get("timestamp", []),
                "equity": [float(v or 0.0) for v in data.get("equity", [])],
                "profit_loss": [float(v or 0.0) for v in data.get("profit_loss", [])],
                "profit_loss_pct": [float(v or 0.0) for v in data.get("profit_loss_pct", [])],
                "base_value": float(data.get("base_value", 0.0) or 0.0),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("AlpacaAdapter.fetch_portfolio_history: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Connection check
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._key,
            "APCA-API-SECRET-KEY": self._secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str) -> Any:
        url = f"{self._base_url}{path}"
        req = urllib.request.Request(url, method=method, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Alpaca HTTP {exc.code} on {path}: {body[:256]}") from exc

    def _data_request(self, method: str, path: str) -> Any:
        url = f"{_DATA_BASE}{path}"
        req = urllib.request.Request(url, method=method, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Alpaca Data HTTP {exc.code} on {path}: {body[:256]}") from exc


def _alpaca_ts_to_ns(ts_str: str) -> int:
    """Convert an Alpaca RFC3339 timestamp string to epoch nanoseconds.

    Alpaca returns ``"2024-01-15T09:30:00Z"`` or with microseconds.
    Falls back to 0 on any parse failure so callers always get an int.
    """
    if not ts_str:
        return 0
    try:
        import datetime
        ts_str = ts_str.rstrip("Z")
        if "." in ts_str:
            dt = datetime.datetime.fromisoformat(ts_str)
        else:
            dt = datetime.datetime.fromisoformat(ts_str)
        dt = dt.replace(tzinfo=datetime.timezone.utc)
        return int(dt.timestamp() * 1_000_000_000)
    except Exception:  # noqa: BLE001
        return 0
