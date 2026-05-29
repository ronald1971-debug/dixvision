"""MetaTrader 5 platform integration (Paper-S4).

Read-only adapter for MT5 terminal data: positions, account info,
history, and signals from Expert Advisors, via the ``MetaTrader5``
Python package (lazy-imported at connect() time).

The MetaTrader5 package is Windows-only and requires a running MT5
terminal on the same machine. This adapter is a pure monitoring surface —
it never places orders. For order execution use a Hummingbot or custom
MT5 bridge adapter.

Credentials are embedded in the MT5 terminal session (login/password set
in the terminal itself); this adapter connects to a named server + login.

__capability_tier__ = 0
__forbidden_tiers__ = (5,)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

__capability_tier__ = 0
__forbidden_tiers__ = (5,)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MT5Position:
    """An MT5 position snapshot."""

    ticket: int
    symbol: str
    side: str  # "buy" | "sell"
    volume: float
    price_open: float
    price_current: float
    profit: float
    swap: float
    comment: str
    magic_number: int
    ts_open_ns: int


@dataclass(frozen=True, slots=True)
class MT5AccountInfo:
    """MT5 account state snapshot."""

    login: int
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level_pct: float
    profit: float
    leverage: int
    currency: str
    server: str


@dataclass(frozen=True, slots=True)
class MT5Signal:
    """Signal from MT5 Expert Advisor (read from trade history)."""

    ea_name: str
    symbol: str
    side: str
    entry_price: float
    stop_loss: float
    take_profit: float
    volume: float
    comment: str
    magic_number: int
    ts_ns: int


class MT5Adapter:
    """Read-only adapter for MetaTrader 5.

    Connects to a running MT5 terminal via the ``MetaTrader5`` Python package.
    Reads positions, account info, EA signals, and historical data.
    Never places orders.

    Requires:
      * Windows OS
      * MetaTrader5 terminal running and logged in
      * ``pip install MetaTrader5``

    Args:
        server: MT5 broker server name (e.g. ``"ICMarkets-Demo"``).
            Empty string uses the currently logged-in server.
        login: MT5 account login number. 0 = use currently logged-in account.
        password: MT5 account password. Empty = use terminal's active session.
        path: Path to the MT5 terminal executable.
            ``None`` = use the registry/default path.
    """

    def __init__(
        self,
        *,
        server: str = "",
        login: int = 0,
        password: str = "",
        path: str | None = None,
    ) -> None:
        self._server = server
        self._login = login
        self._password = password
        self._path = path
        self._connected = False
        self._mt5: Any = None  # MetaTrader5 module (lazy)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Initialize the MT5 terminal connection.

        Returns:
            True if MT5 initialized and logged in successfully.
        """
        try:
            import MetaTrader5 as mt5  # noqa: N813, PLC0415
            self._mt5 = mt5

            init_kwargs: dict[str, Any] = {}
            if self._path:
                init_kwargs["path"] = self._path
            if self._login:
                init_kwargs["login"] = self._login
            if self._password:
                init_kwargs["password"] = self._password
            if self._server:
                init_kwargs["server"] = self._server

            if not mt5.initialize(**init_kwargs):
                error = mt5.last_error()
                logger.error("MT5Adapter: initialize() failed: %s", error)
                return False

            info = mt5.terminal_info()
            account = mt5.account_info()
            logger.info(
                "MT5Adapter: connected terminal=%s account=%s server=%s",
                getattr(info, "name", ""),
                getattr(account, "login", ""),
                getattr(account, "server", ""),
            )
            self._connected = True
            return True

        except ImportError:
            logger.warning("MT5Adapter: MetaTrader5 package not installed — scaffold mode")
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("MT5Adapter: connect failed: %s", exc)
            return False

    def disconnect(self) -> None:
        """Shutdown the MT5 terminal connection."""
        if self._connected and self._mt5 is not None:
            try:
                self._mt5.shutdown()
            except Exception:  # noqa: BLE001
                pass
        self._connected = False
        self._mt5 = None

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def fetch_positions(self) -> list[MT5Position]:
        """Fetch all currently open positions.

        Returns:
            List of :class:`MT5Position` or empty list if not connected.
        """
        if not self._connected or self._mt5 is None:
            return []
        try:
            raw = self._mt5.positions_get()
            if raw is None:
                return []
            positions: list[MT5Position] = []
            for p in raw:
                # MT5 position_type: 0=POSITION_TYPE_BUY, 1=POSITION_TYPE_SELL
                side = "buy" if int(p.type) == 0 else "sell"
                ts_ns = int(p.time) * 1_000_000_000
                positions.append(MT5Position(
                    ticket=int(p.ticket),
                    symbol=str(p.symbol),
                    side=side,
                    volume=float(p.volume),
                    price_open=float(p.price_open),
                    price_current=float(p.price_current),
                    profit=float(p.profit),
                    swap=float(p.swap),
                    comment=str(p.comment),
                    magic_number=int(p.magic),
                    ts_open_ns=ts_ns,
                ))
            return positions
        except Exception as exc:  # noqa: BLE001
            logger.error("MT5Adapter.fetch_positions: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def fetch_account_info(self) -> MT5AccountInfo | None:
        """Fetch account state from the MT5 terminal.

        Returns:
            :class:`MT5AccountInfo` or ``None`` if not connected.
        """
        if not self._connected or self._mt5 is None:
            return None
        try:
            a = self._mt5.account_info()
            if a is None:
                return None
            margin_level = float(a.margin_level) if float(a.margin) > 0.0 else 0.0
            return MT5AccountInfo(
                login=int(a.login),
                balance=float(a.balance),
                equity=float(a.equity),
                margin=float(a.margin),
                free_margin=float(a.margin_free),
                margin_level_pct=margin_level,
                profit=float(a.profit),
                leverage=int(a.leverage),
                currency=str(a.currency),
                server=str(a.server),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("MT5Adapter.fetch_account_info: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Signals (EA trade comments parsed from recent history)
    # ------------------------------------------------------------------

    def fetch_signals(
        self,
        *,
        since_ts_ns: int = 0,
        limit: int = 50,
    ) -> list[MT5Signal]:
        """Fetch EA signals by parsing recent order history.

        MT5 does not expose a native 'signals' API; signals are inferred
        from recently closed deals whose comment field contains the EA name.
        Deals are fetched via history_deals_get() filtered by time.

        Args:
            since_ts_ns: Only return deals newer than this epoch nanosecond.
            limit: Max number of signals to return.

        Returns:
            List of :class:`MT5Signal` inferred from recent deals.
        """
        if not self._connected or self._mt5 is None:
            return []
        try:
            import datetime  # noqa: PLC0415

            since_sec = since_ts_ns // 1_000_000_000 if since_ts_ns else 0
            if since_sec == 0:
                # Default: last 24 hours.
                since_dt = datetime.datetime.utcnow() - datetime.timedelta(days=1)
            else:
                since_dt = datetime.datetime.utcfromtimestamp(since_sec)

            deals = self._mt5.history_deals_get(since_dt, datetime.datetime.utcnow())
            if deals is None:
                return []

            signals: list[MT5Signal] = []
            # MT5 deal_type: 0=DEAL_TYPE_BUY, 1=DEAL_TYPE_SELL
            for d in deals[-limit:]:
                side = "buy" if int(d.type) == 0 else "sell"
                signals.append(MT5Signal(
                    ea_name=str(d.comment) if d.comment else "EA",
                    symbol=str(d.symbol),
                    side=side,
                    entry_price=float(d.price),
                    stop_loss=0.0,
                    take_profit=0.0,
                    volume=float(d.volume),
                    comment=str(d.comment),
                    magic_number=int(d.magic),
                    ts_ns=int(d.time) * 1_000_000_000,
                ))
            return signals
        except Exception as exc:  # noqa: BLE001
            logger.error("MT5Adapter.fetch_signals: %s", exc)
            return []

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def fetch_history(
        self,
        *,
        symbol: str = "",
        since_ts_ns: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch trade history (closed deals) from MT5.

        Args:
            symbol: Filter by symbol. Empty = all symbols.
            since_ts_ns: Only return deals newer than this epoch nanosecond.
            limit: Max deals to return.

        Returns:
            List of dicts with deal details.
        """
        if not self._connected or self._mt5 is None:
            return []
        try:
            import datetime  # noqa: PLC0415

            since_sec = since_ts_ns // 1_000_000_000 if since_ts_ns else 0
            if since_sec == 0:
                since_dt = datetime.datetime.utcnow() - datetime.timedelta(days=30)
            else:
                since_dt = datetime.datetime.utcfromtimestamp(since_sec)

            if symbol:
                deals = self._mt5.history_deals_get(
                    since_dt, datetime.datetime.utcnow(), group=symbol
                )
            else:
                deals = self._mt5.history_deals_get(since_dt, datetime.datetime.utcnow())

            if deals is None:
                return []

            result: list[dict[str, Any]] = []
            for d in deals[-limit:]:
                result.append({
                    "ticket": int(d.ticket),
                    "order": int(d.order),
                    "symbol": str(d.symbol),
                    "type": "buy" if int(d.type) == 0 else "sell",
                    "volume": float(d.volume),
                    "price": float(d.price),
                    "profit": float(d.profit),
                    "commission": float(d.commission),
                    "swap": float(d.swap),
                    "comment": str(d.comment),
                    "magic": int(d.magic),
                    "ts_ns": int(d.time) * 1_000_000_000,
                })
            return result
        except Exception as exc:  # noqa: BLE001
            logger.error("MT5Adapter.fetch_history: symbol=%s error=%s", symbol, exc)
            return []

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def fetch_market_data(
        self,
        *,
        symbol: str,
        timeframe: str = "H1",
        bars: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch OHLCV bars from MT5 terminal.

        Args:
            symbol: MT5 symbol (e.g. ``"EURUSD"``, ``"BTCUSD"``).
            timeframe: MT5 timeframe string: ``"M1"``, ``"M5"``, ``"M15"``,
                ``"M30"``, ``"H1"``, ``"H4"``, ``"D1"``, ``"W1"``, ``"MN1"``.
            bars: Number of bars to fetch (from current bar going back).

        Returns:
            List of dicts with ``time``, ``open``, ``high``, ``low``,
            ``close``, ``tick_volume``, ``real_volume``, ``spread``, ``ts_ns``.
        """
        if not self._connected or self._mt5 is None:
            return []
        try:
            tf_map = {
                "M1": 1, "M5": 5, "M15": 15, "M30": 30,
                "H1": 16385, "H4": 16388,
                "D1": 16408, "W1": 32769, "MN1": 49153,
            }
            tf_const = tf_map.get(timeframe.upper(), 16385)

            rates = self._mt5.copy_rates_from_pos(symbol, tf_const, 0, bars)
            if rates is None:
                return []

            result: list[dict[str, Any]] = []
            for r in rates:
                result.append({
                    "time": int(r[0]),
                    "ts_ns": int(r[0]) * 1_000_000_000,
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "tick_volume": int(r[5]),
                    "spread": int(r[6]),
                    "real_volume": int(r[7]),
                })
            return result
        except Exception as exc:  # noqa: BLE001
            logger.error("MT5Adapter.fetch_market_data: symbol=%s error=%s", symbol, exc)
            return []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Check connection status."""
        if not self._connected or self._mt5 is None:
            return False
        try:
            info = self._mt5.terminal_info()
            return info is not None and bool(info.connected)
        except Exception:  # noqa: BLE001
            return False
