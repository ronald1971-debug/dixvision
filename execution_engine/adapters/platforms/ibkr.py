"""Interactive Brokers integration (Paper-S6).

Read-only adapter for IBKR TWS/Gateway: account data, positions,
market data, and order status monitoring via ``ib_insync``.

ib_insync is lazy-imported at connect() time so the module imports
cleanly without the package installed. Credentials are passed
explicitly — never read from os.environ (INV-65).

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
class IBKRPosition:
    """An IBKR position."""

    contract_id: int
    symbol: str
    sec_type: str  # "STK" | "OPT" | "FUT" | "CRYPTO"
    exchange: str
    currency: str
    quantity: float
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float


@dataclass(frozen=True, slots=True)
class IBKRAccountSummary:
    """IBKR account summary."""

    account_id: str
    net_liquidation: float
    total_cash: float
    buying_power: float
    gross_position_value: float
    unrealized_pnl: float
    realized_pnl: float
    maintenance_margin: float
    currency: str


@dataclass(frozen=True, slots=True)
class IBKRMarketData:
    """IBKR market data tick."""

    symbol: str
    bid: float
    ask: float
    last: float
    volume: int
    open_price: float
    high: float
    low: float
    close: float
    ts_ns: int


class IBKRAdapter:
    """Read-only adapter for Interactive Brokers.

    Connects to TWS or IB Gateway via ib_insync (lazy import) to read
    positions, account data, and market data. Never places orders —
    use execution_engine.adapters.ibkr.IBKRAdapter for that.

    TWS default port: 7497 (paper), 7496 (live).
    IB Gateway default port: 4002 (paper), 4001 (live).

    Args:
        host: TWS/Gateway hostname (default ``"127.0.0.1"``).
        port: TWS/Gateway API port.
        client_id: IB API client ID (must be unique per connection).
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
    ) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._connected = False
        self._ib: Any = None  # ib_insync.IB instance (lazy)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect to TWS/Gateway via ib_insync.

        Returns:
            True if connected successfully.
        """
        try:
            import ib_insync  # noqa: PLC0415
            self._ib = ib_insync.IB()
            self._ib.connect(
                host=self._host,
                port=self._port,
                clientId=self._client_id,
                timeout=10,
                readonly=True,
            )
            self._connected = True
            logger.info(
                "IBKRAdapter (platforms): connected %s:%s client_id=%s",
                self._host, self._port, self._client_id,
            )
            return True
        except ImportError:
            logger.warning("IBKRAdapter (platforms): ib_insync not installed — scaffold mode")
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("IBKRAdapter (platforms): connect failed: %s", exc)
            return False

    def disconnect(self) -> None:
        """Disconnect from TWS/Gateway."""
        if self._ib is not None:
            try:
                self._ib.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._ib = None
        self._connected = False

    # ------------------------------------------------------------------
    # Positions & account
    # ------------------------------------------------------------------

    def fetch_positions(self) -> list[IBKRPosition]:
        """Fetch all positions from TWS/Gateway.

        Returns:
            List of :class:`IBKRPosition` or empty list if not connected.
        """
        if not self._connected or self._ib is None:
            return []
        try:
            raw_positions = self._ib.positions()
            result: list[IBKRPosition] = []
            for p in raw_positions:
                contract = p.contract
                pnl = self._ib.pnl()
                # Find matching PnL entry for this contract.
                unrealized = 0.0
                realized = 0.0
                for entry in pnl:
                    if hasattr(entry, "contract") and entry.contract.conId == contract.conId:
                        unrealized = float(entry.unrealizedPnL or 0.0)
                        realized = float(entry.realizedPnL or 0.0)
                        break

                result.append(IBKRPosition(
                    contract_id=int(contract.conId or 0),
                    symbol=str(contract.symbol or ""),
                    sec_type=str(contract.secType or "STK"),
                    exchange=str(contract.exchange or ""),
                    currency=str(contract.currency or "USD"),
                    quantity=float(p.position or 0.0),
                    avg_cost=float(p.avgCost or 0.0),
                    market_value=float(p.position or 0.0) * float(p.avgCost or 0.0),
                    unrealized_pnl=unrealized,
                    realized_pnl=realized,
                ))
            return result
        except Exception as exc:  # noqa: BLE001
            logger.error("IBKRAdapter.fetch_positions: %s", exc)
            return []

    def fetch_account_summary(self) -> IBKRAccountSummary | None:
        """Fetch account summary from TWS/Gateway.

        Returns:
            :class:`IBKRAccountSummary` or ``None`` if not connected.
        """
        if not self._connected or self._ib is None:
            return None
        try:
            accounts = self._ib.managedAccounts()
            account_id = accounts[0] if accounts else ""
            summary_items = self._ib.accountSummary(account=account_id)

            fields: dict[str, float] = {}
            currency = "USD"
            for item in summary_items:
                tag = str(item.tag)
                try:
                    fields[tag] = float(item.value or 0.0)
                except (TypeError, ValueError):
                    pass
                if tag == "Currency":
                    currency = str(item.value or "USD")

            return IBKRAccountSummary(
                account_id=account_id,
                net_liquidation=fields.get("NetLiquidation", 0.0),
                total_cash=fields.get("TotalCashValue", 0.0),
                buying_power=fields.get("BuyingPower", 0.0),
                gross_position_value=fields.get("GrossPositionValue", 0.0),
                unrealized_pnl=fields.get("UnrealizedPnL", 0.0),
                realized_pnl=fields.get("RealizedPnL", 0.0),
                maintenance_margin=fields.get("MaintMarginReq", 0.0),
                currency=currency,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("IBKRAdapter.fetch_account_summary: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def fetch_market_data(
        self,
        *,
        symbol: str,
        sec_type: str = "STK",
        exchange: str = "SMART",
    ) -> IBKRMarketData | None:
        """Fetch a snapshot of market data for a symbol.

        Args:
            symbol: IB symbol (e.g. ``"AAPL"``).
            sec_type: IB security type (``"STK"``, ``"FUT"``, ``"CASH"`` for forex).
            exchange: IB routing exchange.

        Returns:
            :class:`IBKRMarketData` snapshot or ``None`` on error.
        """
        if not self._connected or self._ib is None:
            return None
        try:
            import ib_insync  # noqa: PLC0415
            from system import time_source  # noqa: PLC0415

            if sec_type == "CASH":
                contract = ib_insync.Forex(symbol)
            elif sec_type == "FUT":
                contract = ib_insync.Future(symbol=symbol, exchange=exchange)
            else:
                contract = ib_insync.Stock(symbol=symbol, exchange=exchange, currency="USD")

            tickers = self._ib.reqTickers(contract)
            if not tickers:
                return None
            t = tickers[0]
            return IBKRMarketData(
                symbol=symbol,
                bid=float(t.bid or 0.0),
                ask=float(t.ask or 0.0),
                last=float(t.last or 0.0),
                volume=int(t.volume or 0),
                open_price=float(t.open or 0.0),
                high=float(t.high or 0.0),
                low=float(t.low or 0.0),
                close=float(t.close or 0.0),
                ts_ns=time_source.wall_ns(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("IBKRAdapter.fetch_market_data: symbol=%s error=%s", symbol, exc)
            return None

    def fetch_historical_data(
        self,
        *,
        symbol: str,
        duration: str = "1 Y",
        bar_size: str = "1 day",
        sec_type: str = "STK",
    ) -> list[dict[str, Any]]:
        """Fetch historical OHLCV bars for a symbol via reqHistoricalData.

        Args:
            symbol: IB symbol.
            duration: IB duration string (``"1 D"``, ``"1 W"``, ``"1 Y"``).
            bar_size: IB bar size (``"1 min"``, ``"1 hour"``, ``"1 day"``).
            sec_type: IB security type.

        Returns:
            List of dicts with ``date``, ``open``, ``high``, ``low``,
            ``close``, ``volume``, ``average``, ``barCount`` keys.
        """
        if not self._connected or self._ib is None:
            return []
        try:
            import datetime  # noqa: PLC0415
            import ib_insync  # noqa: PLC0415

            if sec_type == "CASH":
                contract = ib_insync.Forex(symbol)
            elif sec_type == "FUT":
                contract = ib_insync.Future(symbol=symbol, exchange="CME")
            else:
                contract = ib_insync.Stock(symbol=symbol, exchange="SMART", currency="USD")

            bars = self._ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
            )
            return [
                {
                    "date": str(b.date),
                    "open": float(b.open),
                    "high": float(b.high),
                    "low": float(b.low),
                    "close": float(b.close),
                    "volume": int(b.volume),
                    "average": float(b.average),
                    "bar_count": int(b.barCount),
                }
                for b in bars
            ]
        except Exception as exc:  # noqa: BLE001
            logger.error("IBKRAdapter.fetch_historical_data: symbol=%s error=%s", symbol, exc)
            return []

    def fetch_order_status(self, *, order_id: int) -> dict[str, Any]:
        """Fetch the status of an order by IB orderId.

        Args:
            order_id: IB numeric order ID.

        Returns:
            Dict with ``order_id``, ``status``, ``filled``, ``remaining``,
            ``avg_fill_price``, ``perm_id`` keys, or empty dict if not found.
        """
        if not self._connected or self._ib is None:
            return {}
        try:
            trades = self._ib.trades()
            for trade in trades:
                if trade.order.orderId == order_id:
                    os = trade.orderStatus
                    return {
                        "order_id": order_id,
                        "status": str(os.status),
                        "filled": float(os.filled),
                        "remaining": float(os.remaining),
                        "avg_fill_price": float(os.avgFillPrice),
                        "perm_id": int(os.permId),
                        "last_fill_price": float(os.lastFillPrice),
                        "why_held": str(os.whyHeld or ""),
                    }
            return {}
        except Exception as exc:  # noqa: BLE001
            logger.error("IBKRAdapter.fetch_order_status: order_id=%s error=%s", order_id, exc)
            return {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Check connection status."""
        return self._connected and self._ib is not None and self._ib.isConnected()
