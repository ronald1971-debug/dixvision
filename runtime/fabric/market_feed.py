"""Market Feed — WebSocket + REST data ingestion into the IngestionBus.

Connects to exchange market data streams and pushes normalized ticks
into the IngestionBus for the kernel tick loop to consume.

Supported sources:
- Alpaca CryptoDataStream (WebSocket, FREE, no API keys needed)
- Alpaca CryptoHistoricalDataClient (REST backfill)
- CCXT WebSocket streams (Binance, Coinbase, Kraken)
- CCXTExecutionBridge REST polling (fallback)

For the full list of ALL data sources (news, sentiment, on-chain,
macro, learning, etc.) see ``source_registry.py``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from runtime.fabric.ingestion_bus import IngestedTick, IngestionBus, IngestionSource
from system import time_source

logger = logging.getLogger(__name__)


class MarketFeed:
    """Pushes market data into the IngestionBus from exchange sources.

    Supports three modes (in priority order):
    1. Alpaca crypto stream (WebSocket, free, no keys)
    2. CCXT Pro WebSocket (when available)
    3. REST polling via CCXTExecutionBridge or Alpaca historical (fallback)

    The feed normalizes all data into IngestedTick before submission.
    """

    def __init__(
        self,
        *,
        ingestion_bus: IngestionBus,
        poll_interval_ms: float = 1000.0,
    ) -> None:
        self._bus = ingestion_bus
        self._poll_interval_s = poll_interval_ms / 1000.0
        self._running = False
        self._bridges: dict[str, Any] = {}
        self._ws_connections: dict[str, Any] = {}
        self._symbols: list[str] = []
        self._ws_available = False
        self._alpaca_stream: Any = None
        self._alpaca_symbols: list[str] = []

    def register_bridge(
        self,
        exchange_id: str,
        bridge: Any,
        symbols: list[str],
    ) -> None:
        """Register a CCXTExecutionBridge for REST polling."""
        self._bridges[exchange_id] = bridge
        self._symbols.extend(symbols)

    def register_alpaca(self, symbols: list[str] | None = None) -> None:
        """Register Alpaca crypto as a data source.

        No API keys required for crypto market data.
        """
        self._alpaca_symbols = symbols or ["BTC/USD", "ETH/USD", "SOL/USD"]

    async def start_alpaca_stream(self) -> bool:
        """Start Alpaca's CryptoDataStream for real-time data.

        Returns True if stream was initialized (no keys needed).
        """
        if not self._alpaca_symbols:
            return False

        try:
            from integrations.alpaca.crypto_feed import AlpacaCryptoStream

            self._alpaca_stream = AlpacaCryptoStream(symbols=self._alpaca_symbols)
            self._ws_available = True
            logger.info("Alpaca crypto stream registered: %s", self._alpaca_symbols)
            return True
        except Exception as e:
            logger.warning("Failed to init Alpaca stream: %s", e)
            return False

    async def start_websocket(
        self,
        exchange_id: str,
        symbols: list[str],
    ) -> bool:
        """Start a CCXT Pro WebSocket stream for real-time data.

        Returns False if CCXT Pro is not available (falls back to REST).
        """
        try:
            import ccxt.pro as ccxtpro  # noqa: F401
        except ImportError:
            logger.info("CCXT Pro not available — using REST polling for %s", exchange_id)
            return False

        try:
            exchange_class = getattr(ccxtpro, exchange_id, None)
            if exchange_class is None:
                logger.warning("Exchange %s not supported by CCXT Pro", exchange_id)
                return False

            ws_exchange = exchange_class({"enableRateLimit": True})
            self._ws_connections[exchange_id] = (ws_exchange, symbols)
            self._ws_available = True
            logger.info("WebSocket feed started for %s: %s", exchange_id, symbols)
            return True
        except Exception as e:
            logger.warning("Failed to start WebSocket for %s: %s", exchange_id, e)
            return False

    async def run(self) -> None:
        """Run the market feed — streams or polls data into the bus."""
        self._running = True

        tasks: list[asyncio.Task[None]] = []

        # Priority 1: Alpaca crypto stream (free, no keys)
        if self._alpaca_stream is not None:
            tasks.append(asyncio.create_task(self._alpaca_ws_loop()))

        # Priority 2: CCXT Pro WebSocket tasks
        for exchange_id, (ws_exchange, symbols) in self._ws_connections.items():
            task = asyncio.create_task(self._ws_loop(exchange_id, ws_exchange, symbols))
            tasks.append(task)

        # Priority 3: REST polling for remaining bridges
        ws_exchanges = set(self._ws_connections.keys())
        for exchange_id, bridge in self._bridges.items():
            if exchange_id not in ws_exchanges:
                symbols = list(self._symbols)
                task = asyncio.create_task(self._poll_loop(exchange_id, bridge, symbols))
                tasks.append(task)

        # Priority 4: Alpaca historical polling fallback
        if self._alpaca_stream is None and self._alpaca_symbols:
            tasks.append(asyncio.create_task(self._alpaca_poll_loop()))

        if not tasks:
            logger.info("No market data sources configured — feed idle")
            while self._running:
                await asyncio.sleep(1.0)
            return

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass

    async def _alpaca_ws_loop(self) -> None:
        """Run Alpaca WebSocket stream, pushing bars into the bus."""
        if self._alpaca_stream is None:
            return

        async def on_bar(bar: Any) -> None:
            tick = IngestedTick(
                source=IngestionSource.ALPACA_WS,
                symbol=bar.symbol,
                price=bar.close,
                volume=bar.volume,
                ts_ns=bar.ts_ns,
                raw_payload={
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "vwap": bar.vwap,
                    "trade_count": bar.trade_count,
                    "source": "alpaca",
                },
            )
            await self._bus.ingest(tick)

        try:
            await self._alpaca_stream.start(on_bar=on_bar)
        except Exception as e:
            if self._running:
                logger.warning("Alpaca WS stream error: %s", e)
                # Fall back to polling
                await self._alpaca_poll_loop()

    async def _alpaca_poll_loop(self) -> None:
        """REST polling from Alpaca historical API (fallback)."""
        try:
            from integrations.alpaca.crypto_feed import AlpacaCryptoHistorical

            historical = AlpacaCryptoHistorical()
        except Exception as e:
            logger.warning("Alpaca historical client unavailable: %s", e)
            return

        while self._running:
            for symbol in self._alpaca_symbols:
                try:
                    bar = historical.get_latest_bar(symbol)
                    if bar is not None:
                        tick = IngestedTick(
                            source=IngestionSource.ALPACA_REST,
                            symbol=bar.symbol,
                            price=bar.close,
                            volume=bar.volume,
                            ts_ns=time_source.wall_ns(),
                            raw_payload={
                                "open": bar.open,
                                "high": bar.high,
                                "low": bar.low,
                                "close": bar.close,
                                "vwap": bar.vwap,
                                "source": "alpaca",
                            },
                        )
                        await self._bus.ingest(tick)
                except Exception as e:
                    logger.debug("Alpaca poll error %s: %s", symbol, e)

            await asyncio.sleep(self._poll_interval_s)

    async def _ws_loop(
        self,
        exchange_id: str,
        ws_exchange: Any,
        symbols: list[str],
    ) -> None:
        """WebSocket streaming loop for a single exchange."""
        source = _exchange_source(exchange_id)

        while self._running:
            for symbol in symbols:
                try:
                    ticker = await ws_exchange.watch_ticker(symbol)
                    tick = IngestedTick(
                        source=source,
                        symbol=symbol,
                        price=float(ticker.get("last", 0)),
                        volume=float(ticker.get("baseVolume", 0)),
                        ts_ns=time_source.wall_ns(),
                        raw_payload=dict(ticker),
                    )
                    await self._bus.ingest(tick)
                except Exception as e:
                    logger.warning("WS tick error %s/%s: %s", exchange_id, symbol, e)
                    await asyncio.sleep(1.0)

    async def _poll_loop(
        self,
        exchange_id: str,
        bridge: Any,
        symbols: list[str],
    ) -> None:
        """REST polling loop for a single exchange bridge."""
        source = _exchange_source(exchange_id)

        while self._running:
            for symbol in symbols:
                try:
                    snapshot = bridge.get_ticker(symbol)
                    if snapshot is not None:
                        tick = IngestedTick(
                            source=source,
                            symbol=symbol,
                            price=snapshot.last,
                            volume=snapshot.volume_24h,
                            ts_ns=time_source.wall_ns(),
                        )
                        await self._bus.ingest(tick)
                except Exception as e:
                    logger.debug("REST poll error %s/%s: %s", exchange_id, symbol, e)

            await asyncio.sleep(self._poll_interval_s)

    def stop(self) -> None:
        """Signal the feed to stop."""
        self._running = False

        # Stop Alpaca stream
        if self._alpaca_stream is not None:
            self._alpaca_stream.stop()

        # Close CCXT Pro WebSocket connections
        for _exchange_id, (ws_exchange, _) in self._ws_connections.items():
            try:
                if hasattr(ws_exchange, "close"):
                    asyncio.get_event_loop().create_task(ws_exchange.close())
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def ws_available(self) -> bool:
        return self._ws_available


def _exchange_source(exchange_id: str) -> IngestionSource:
    """Map exchange ID to IngestionSource enum."""
    mapping = {
        "binance": IngestionSource.BINANCE_WS,
        "raydium": IngestionSource.RAYDIUM_WS,
        "pumpfun": IngestionSource.PUMPFUN_WS,
    }
    return mapping.get(exchange_id, IngestionSource.REST_POLL)
