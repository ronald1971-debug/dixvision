"""Alpaca Crypto Feed — real market data via alpaca-py SDK.

Provides two interfaces:
1. ``AlpacaCryptoHistorical`` — fetch historical OHLCV bars (backfill,
   backtesting, replay seed data)
2. ``AlpacaCryptoStream`` — real-time bar/trade/quote streaming via
   WebSocket (live IngestionBus feed)

Crypto data is FREE and requires NO API keys.  If trading API keys are
provided (for order execution), they can be passed separately.

Usage:
    # Historical (no keys needed)
    feed = AlpacaCryptoHistorical()
    bars = feed.get_bars("BTC/USD", timeframe="1h", limit=100)

    # Real-time streaming (no keys needed for crypto)
    stream = AlpacaCryptoStream(symbols=["BTC/USD", "ETH/USD"])
    await stream.start(on_bar=callback)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from system import time_source

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CryptoBar:
    """Normalized crypto bar from Alpaca."""

    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int
    vwap: float
    timestamp_utc: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class CryptoQuote:
    """Normalized crypto quote from Alpaca."""

    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    ts_ns: int


class AlpacaCryptoHistorical:
    """Fetch historical crypto bars from Alpaca.

    No API keys required — crypto market data is freely available.
    """

    def __init__(self) -> None:
        from alpaca.data.historical import CryptoHistoricalDataClient

        self._client = CryptoHistoricalDataClient()

    def get_bars(
        self,
        symbol: str,
        *,
        timeframe: str = "1h",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[CryptoBar]:
        """Fetch historical bars for a crypto symbol.

        Parameters
        ----------
        symbol : str
            Crypto pair, e.g. "BTC/USD", "ETH/USD".
        timeframe : str
            Bar timeframe: "1m", "5m", "15m", "1h", "1d".
        start : datetime, optional
            Start time (UTC).
        end : datetime, optional
            End time (UTC).
        limit : int
            Max bars to return (default 100).
        """
        from alpaca.data.requests import CryptoBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        tf_map: dict[str, TimeFrame] = {
            "1m": TimeFrame(1, TimeFrameUnit.Minute),
            "5m": TimeFrame(5, TimeFrameUnit.Minute),
            "15m": TimeFrame(15, TimeFrameUnit.Minute),
            "1h": TimeFrame(1, TimeFrameUnit.Hour),
            "1d": TimeFrame(1, TimeFrameUnit.Day),
        }
        tf = tf_map.get(timeframe, TimeFrame(1, TimeFrameUnit.Hour))

        request_params = CryptoBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=tf,
            start=start,
            end=end,
            limit=limit,
        )

        raw_bars = self._client.get_crypto_bars(request_params)
        bars: list[CryptoBar] = []

        # raw_bars is a BarSet — index by symbol to get list of Bar
        symbols = [symbol] if isinstance(symbol, str) else list(symbol)
        for sym in symbols:
            try:
                bar_list = raw_bars[sym]
            except (KeyError, IndexError):
                continue
            for bar in bar_list:
                bars.append(
                    CryptoBar(
                        symbol=str(bar.symbol),
                        open=float(bar.open),
                        high=float(bar.high),
                        low=float(bar.low),
                        close=float(bar.close),
                        volume=float(bar.volume),
                        trade_count=int(bar.trade_count),
                        vwap=float(bar.vwap),
                        timestamp_utc=str(bar.timestamp),
                        ts_ns=int(bar.timestamp.timestamp() * 1e9),
                    )
                )

        logger.info("Fetched %d bars for %s (%s)", len(bars), symbol, timeframe)
        return bars

    def get_latest_bar(self, symbol: str) -> CryptoBar | None:
        """Fetch the most recent bar for a symbol."""
        bars = self.get_bars(symbol, timeframe="1m", limit=1)
        return bars[-1] if bars else None


class AlpacaCryptoStream:
    """Real-time crypto data streaming via Alpaca WebSocket.

    Connects to Alpaca's CryptoDataStream for live bar/trade/quote
    updates. No API keys required for crypto.
    """

    def __init__(
        self,
        *,
        symbols: list[str] | None = None,
        api_key: str = "",
        api_secret: str = "",
    ) -> None:
        self._symbols = symbols or ["BTC/USD", "ETH/USD", "SOL/USD"]
        self._api_key = api_key
        self._api_secret = api_secret
        self._stream = None
        self._running = False
        self._on_bar: Callable[[CryptoBar], Any] | None = None
        self._on_quote: Callable[[CryptoQuote], Any] | None = None

    async def start(
        self,
        *,
        on_bar: Callable[[CryptoBar], Any] | None = None,
        on_quote: Callable[[CryptoQuote], Any] | None = None,
    ) -> None:
        """Start the WebSocket stream.

        Callbacks are invoked on each bar/quote update.
        """
        from alpaca.data.live import CryptoDataStream

        self._on_bar = on_bar
        self._on_quote = on_quote
        self._running = True

        # CryptoDataStream accepts empty strings for no-auth crypto
        self._stream = CryptoDataStream(
            api_key=self._api_key or "none",
            secret_key=self._api_secret or "none",
        )

        if on_bar:
            self._stream.subscribe_bars(self._handle_bar, *self._symbols)

        if on_quote:
            self._stream.subscribe_quotes(self._handle_quote, *self._symbols)

        logger.info("Alpaca crypto stream starting for %s", self._symbols)

        try:
            await asyncio.to_thread(self._stream.run)
        except Exception as e:
            if self._running:
                logger.warning("Alpaca stream error: %s", e)

    async def _handle_bar(self, bar: Any) -> None:
        """Handle incoming bar from Alpaca stream."""
        if self._on_bar is None:
            return

        crypto_bar = CryptoBar(
            symbol=str(bar.symbol),
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=float(bar.volume),
            trade_count=int(bar.trade_count),
            vwap=float(bar.vwap),
            timestamp_utc=str(bar.timestamp),
            ts_ns=time_source.wall_ns(),
        )
        self._on_bar(crypto_bar)

    async def _handle_quote(self, quote: Any) -> None:
        """Handle incoming quote from Alpaca stream."""
        if self._on_quote is None:
            return

        crypto_quote = CryptoQuote(
            symbol=str(quote.symbol),
            bid=float(quote.bid_price),
            ask=float(quote.ask_price),
            bid_size=float(quote.bid_size),
            ask_size=float(quote.ask_size),
            ts_ns=time_source.wall_ns(),
        )
        self._on_quote(crypto_quote)

    def stop(self) -> None:
        """Stop the WebSocket stream."""
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        return self._running
