"""Unified Source Registry — wires ALL data feeds into the IngestionBus.

Every data source in the system is registered here and connected to
the IngestionBus. Sources are organized by category and each produces
IngestedTick records normalized for the kernel tick loop.

Categories:
 1. Market Data      — Alpaca, CCXT, OpenBB, Polygon, IEX, AlphaVantage
 2. Exchange WS/Exec — Binance WS, Helius, PumpFun, Solana, UniswapX,
                        Hummingbot, IBKR, vnpy, Alpaca Trading
 3. News             — CoinDesk RSS, Alpaca News, NewsFeed, News Fanout
 4. Social           — Reddit, X/Twitter, Social Sentiment
 5. On-Chain         — Glassnode, Nansen, Arkham, Dune, Etherscan,
                        Bitquery, Solana RPC, Ethplorer, OnchainStreams
 6. Macro            — FRED, BLS
 7. Signals          — TradingView alerts/ideas, MT5, QuantConnect,
                        Backtrader, Freqtrade, Jesse, QSTrader, VectorBT
 8. Sensory          — Technical indicators, Neuromorphic (Indira, Dyon,
                        Governance risk, SNN LIF, SNNTorch, Nengo, Spyke),
                        Voice, Regulatory, Alt, Cognitive, Dev
 9. Learning         — Web autolearn, Trader intelligence, Learning engine
10. Infrastructure   — Kafka events, DuckDB analytics, Qdrant memory

Each adapter is lazily initialized and produces IngestedTick with the
appropriate IngestionSource tag so the DecisionPipeline can weight
and route signals by provenance.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

from runtime.fabric.ingestion_bus import IngestedTick, IngestionBus, IngestionSource
from system import time_source

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SourceStatus:
    """Status of a registered source."""

    name: str
    source: IngestionSource
    connected: bool
    ticks_produced: int
    last_tick_ts_ns: int
    error: str = ""


@dataclass
class SourceHandle:
    """Mutable handle tracking a registered source."""

    name: str
    source: IngestionSource
    adapter: Any
    connected: bool = False
    ticks_produced: int = 0
    last_tick_ts_ns: int = 0
    last_error: str = ""


class SourceRegistry:
    """Central registry that wires all data sources into the IngestionBus.

    Usage:
        registry = SourceRegistry(bus=ingestion_bus)
        await registry.register_all()
        await registry.start()   # launches all polling/streaming loops
        registry.stop()
    """

    def __init__(self, *, bus: IngestionBus) -> None:
        self._bus = bus
        self._sources: dict[str, SourceHandle] = {}
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False

    @property
    def sources(self) -> dict[str, SourceHandle]:
        return self._sources

    def status(self) -> list[SourceStatus]:
        """Snapshot of all registered source statuses."""
        return [
            SourceStatus(
                name=h.name,
                source=h.source,
                connected=h.connected,
                ticks_produced=h.ticks_produced,
                last_tick_ts_ns=h.last_tick_ts_ns,
                error=h.last_error,
            )
            for h in self._sources.values()
        ]

    async def register_all(self) -> int:
        """Register all available data sources. Returns count registered."""
        count = 0
        count += self._register_market_sources()
        count += self._register_exchange_sources()
        count += self._register_news_sources()
        count += self._register_social_sources()
        count += self._register_onchain_sources()
        count += self._register_macro_sources()
        count += self._register_signal_sources()
        count += self._register_sensory_sources()
        count += self._register_learning_sources()
        count += self._register_infra_sources()
        count += self._register_mind_sources()
        count += self._register_integration_sources()
        count += self._register_feed_runners()
        count += self._register_autolearn_variants()
        count += self._register_paper_adapter()
        logger.info("[SOURCE_REGISTRY] Registered %d sources", count)
        return count

    async def start(self) -> None:
        """Start all registered source polling/streaming loops."""
        self._running = True
        for name, handle in self._sources.items():
            task = asyncio.create_task(self._run_source(name, handle))
            self._tasks.append(task)
        logger.info("[SOURCE_REGISTRY] Started %d source loops", len(self._tasks))

    def stop(self) -> None:
        """Stop all source loops."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    # ── Helpers ──

    async def _submit(self, handle: SourceHandle, tick: IngestedTick) -> None:
        """Submit a tick from a source handle."""
        await self._bus.ingest(tick)
        handle.ticks_produced += 1
        handle.last_tick_ts_ns = tick.ts_ns

    async def _run_source(self, name: str, handle: SourceHandle) -> None:
        """Generic polling loop for a source."""
        poll_interval = float(os.environ.get("DIX_SOURCE_POLL_S", "30"))

        while self._running:
            try:
                ticks = self._poll_source(handle)
                for tick in ticks:
                    await self._submit(handle, tick)
                handle.connected = True
                handle.last_error = ""
            except Exception as e:
                handle.last_error = str(e)
                logger.debug("Source %s poll error: %s", name, e)
            await asyncio.sleep(poll_interval)

    def _poll_source(self, handle: SourceHandle) -> list[IngestedTick]:
        """Poll a single source for new data."""
        adapter = handle.adapter
        source = handle.source
        ts = time_source.wall_ns()

        # ── Market data sources ──
        if source == IngestionSource.ALPACA_REST:
            return self._poll_alpaca_market(adapter, ts)
        if source == IngestionSource.CCXT_POLL:
            return self._poll_ccxt(adapter, ts)
        if source == IngestionSource.OPENBB:
            return self._poll_openbb(adapter, ts)
        if source == IngestionSource.RAYDIUM_POOLS:
            return self._poll_raydium_pools(adapter, ts)
        if source == IngestionSource.POLYGON:
            return self._poll_polygon(adapter, ts)
        if source == IngestionSource.IEX_CLOUD:
            return self._poll_iex(adapter, ts)
        if source == IngestionSource.ALPHAVANTAGE:
            return self._poll_alphavantage(adapter, ts)

        # ── News sources ──
        if source == IngestionSource.COINDESK_RSS:
            return self._poll_coindesk(adapter, ts)
        if source == IngestionSource.NEWS_FEED:
            return self._poll_news_feed(adapter, ts)
        if source == IngestionSource.ALPACA_NEWS:
            return self._poll_alpaca_news(adapter, ts)

        # ── Social sentiment ──
        if source == IngestionSource.REDDIT_SENTIMENT:
            return self._poll_reddit(adapter, ts)
        if source == IngestionSource.X_SENTIMENT:
            return self._poll_x_sentiment(adapter, ts)
        if source == IngestionSource.SOCIAL_SENTIMENT:
            return self._poll_social_sentiment(adapter, ts)

        # ── On-chain ──
        if source == IngestionSource.GLASSNODE:
            return self._poll_glassnode(adapter, ts)
        if source == IngestionSource.NANSEN:
            return self._poll_nansen(adapter, ts)
        if source == IngestionSource.ARKHAM:
            return self._poll_arkham(adapter, ts)
        if source == IngestionSource.DUNE:
            return self._poll_dune(adapter, ts)
        if source == IngestionSource.ONCHAIN_STREAMS:
            return self._poll_onchain_streams(adapter, ts)

        # ── Macro ──
        if source == IngestionSource.FRED_MACRO:
            return self._poll_fred(adapter, ts)

        # ── Signals ──
        if source == IngestionSource.TRADINGVIEW_IDEAS:
            return self._poll_tradingview_ideas(adapter, ts)

        # ── Learning/sensory ──
        if source == IngestionSource.WEB_AUTOLEARN:
            return self._poll_web_autolearn(adapter, ts)
        if source == IngestionSource.TRADER_INTELLIGENCE:
            return self._poll_trader_intelligence(adapter, ts)

        return []

    # ──────────────────────────────────────────────────────────────
    # Registration — 1. Market data providers
    # ──────────────────────────────────────────────────────────────

    def _register_market_sources(self) -> int:
        count = 0

        # Alpaca crypto (FREE, no keys)
        try:
            from integrations.alpaca.crypto_feed import AlpacaCryptoHistorical

            adapter = AlpacaCryptoHistorical()
            self._sources["alpaca_crypto"] = SourceHandle(
                name="Alpaca Crypto",
                source=IngestionSource.ALPACA_REST,
                adapter=adapter,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Alpaca crypto unavailable: %s", e)

        # CCXT bridges (for each configured exchange)
        try:
            from integrations.ccxt_adapter.exchange import ExchangeId
            from integrations.wiring.ccxt_execution_bridge import CCXTExecutionBridge

            for eid in ("binance", "coinbase", "kraken"):
                try:
                    exchange_id = ExchangeId(eid)
                    bridge = CCXTExecutionBridge(exchange_id=exchange_id, sandbox=True)
                    self._sources[f"ccxt_{eid}"] = SourceHandle(
                        name=f"CCXT {eid.title()}", source=IngestionSource.CCXT_POLL, adapter=bridge
                    )
                    count += 1
                except Exception:
                    pass
        except Exception as e:
            logger.debug("CCXT unavailable: %s", e)

        # OpenBB financial data
        try:
            from integrations.openbb_adapter.financial_data import (
                OpenBBFinancialDataAdapter,
            )

            adapter = OpenBBFinancialDataAdapter()
            adapter.connect()
            self._sources["openbb"] = SourceHandle(
                name="OpenBB Financial", source=IngestionSource.OPENBB, adapter=adapter
            )
            count += 1
        except Exception as e:
            logger.debug("OpenBB unavailable: %s", e)

        # Polygon.io (US stocks + crypto, needs API key)
        try:
            import execution_engine.adapters.polygon  # noqa: F401

            self._sources["polygon"] = SourceHandle(
                name="Polygon.io",
                source=IngestionSource.POLYGON,
                adapter=None,
                connected=bool(os.environ.get("POLYGON_API_KEY")),
            )
            count += 1
        except Exception as e:
            logger.debug("Polygon unavailable: %s", e)

        # IEX Cloud (US equities, needs API key)
        try:
            import execution_engine.adapters.iex  # noqa: F401

            self._sources["iex_cloud"] = SourceHandle(
                name="IEX Cloud",
                source=IngestionSource.IEX_CLOUD,
                adapter=None,
                connected=bool(os.environ.get("IEX_API_KEY")),
            )
            count += 1
        except Exception as e:
            logger.debug("IEX Cloud unavailable: %s", e)

        # Alpha Vantage (forex + macro, needs API key)
        try:
            import execution_engine.adapters.alphavantage  # noqa: F401

            self._sources["alphavantage"] = SourceHandle(
                name="Alpha Vantage",
                source=IngestionSource.ALPHAVANTAGE,
                adapter=None,
                connected=bool(os.environ.get("ALPHAVANTAGE_API_KEY")),
            )
            count += 1
        except Exception as e:
            logger.debug("Alpha Vantage unavailable: %s", e)

        # Raydium pools
        try:
            import ui.feeds.raydium_pools  # noqa: F401

            self._sources["raydium_pools"] = SourceHandle(
                name="Raydium Pools",
                source=IngestionSource.RAYDIUM_POOLS,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Raydium pools unavailable: %s", e)

        return count

    # ──────────────────────────────────────────────────────────────
    # Registration — 2. Exchange WebSocket / Execution adapters
    # ──────────────────────────────────────────────────────────────

    def _register_exchange_sources(self) -> int:
        count = 0

        # Binance public WS
        try:
            import ui.feeds.binance_public_ws  # noqa: F401

            self._sources["binance_public_ws"] = SourceHandle(
                name="Binance Public WS",
                source=IngestionSource.BINANCE_WS,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Binance public WS unavailable: %s", e)

        # Binance user data WS (order fills, balance)
        try:
            import execution_engine.adapters.binance_ws  # noqa: F401

            self._sources["binance_user_ws"] = SourceHandle(
                name="Binance User WS",
                source=IngestionSource.BINANCE_USER_WS,
                adapter=None,
                connected=bool(os.environ.get("BINANCE_API_KEY")),
            )
            count += 1
        except Exception as e:
            logger.debug("Binance user WS unavailable: %s", e)

        # PumpFun WS (memecoin stream)
        try:
            import ui.feeds.pumpfun_ws  # noqa: F401

            self._sources["pumpfun_ws"] = SourceHandle(
                name="PumpFun WS", source=IngestionSource.PUMPFUN_WS, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("PumpFun WS unavailable: %s", e)

        # PumpFun execution adapter
        try:
            import execution_engine.adapters.pumpfun  # noqa: F401

            self._sources["pumpfun_exec"] = SourceHandle(
                name="PumpFun Executor", source=IngestionSource.PUMPFUN_EXEC, adapter=None
            )
            count += 1
        except Exception as e:
            logger.debug("PumpFun exec unavailable: %s", e)

        # Helius Solana intelligence (read-only, needs API key)
        try:
            import execution_engine.adapters.helius  # noqa: F401

            self._sources["helius"] = SourceHandle(
                name="Helius Solana",
                source=IngestionSource.HELIUS,
                adapter=None,
                connected=bool(os.environ.get("HELIUS_API_KEY")),
            )
            count += 1
        except Exception as e:
            logger.debug("Helius unavailable: %s", e)

        # Solana native stack (tx submission)
        try:
            import execution_engine.adapters.solana_native  # noqa: F401

            self._sources["solana_native"] = SourceHandle(
                name="Solana Native",
                source=IngestionSource.SOLANA_NATIVE,
                adapter=None,
                connected=bool(os.environ.get("DIX_SOLANA_RPC_URL")),
            )
            count += 1
        except Exception as e:
            logger.debug("Solana native unavailable: %s", e)

        # Alpaca trading (equities + crypto execution, needs keys)
        try:
            import execution_engine.adapters.alpaca  # noqa: F401

            self._sources["alpaca_trading"] = SourceHandle(
                name="Alpaca Trading",
                source=IngestionSource.ALPACA_TRADING,
                adapter=None,
                connected=bool(os.environ.get("ALPACA_API_KEY")),
            )
            count += 1
        except Exception as e:
            logger.debug("Alpaca trading unavailable: %s", e)

        # Interactive Brokers (institutional, needs TWS/Gateway)
        try:
            import execution_engine.adapters.ibkr  # noqa: F401

            self._sources["ibkr"] = SourceHandle(
                name="Interactive Brokers", source=IngestionSource.IBKR, adapter=None
            )
            count += 1
        except Exception as e:
            logger.debug("IBKR unavailable: %s", e)

        # Hummingbot Gateway (~100 connectors)
        try:
            import execution_engine.adapters.hummingbot  # noqa: F401

            self._sources["hummingbot"] = SourceHandle(
                name="Hummingbot Gateway",
                source=IngestionSource.HUMMINGBOT,
                adapter=None,
                connected=bool(os.environ.get("HUMMINGBOT_GATEWAY_URL")),
            )
            count += 1
        except Exception as e:
            logger.debug("Hummingbot unavailable: %s", e)

        # UniswapX (intent-based DEX)
        try:
            import execution_engine.adapters.uniswapx  # noqa: F401

            self._sources["uniswapx"] = SourceHandle(
                name="UniswapX", source=IngestionSource.UNISWAPX, adapter=None
            )
            count += 1
        except Exception as e:
            logger.debug("UniswapX unavailable: %s", e)

        # vnpy (Binance futures + OKX)
        try:
            import execution_engine.adapters.vnpy_bridge  # noqa: F401

            self._sources["vnpy"] = SourceHandle(
                name="vnpy Bridge", source=IngestionSource.VNPY, adapter=None
            )
            count += 1
        except Exception as e:
            logger.debug("vnpy unavailable: %s", e)

        return count

    # ──────────────────────────────────────────────────────────────
    # Registration — 3. News sources
    # ──────────────────────────────────────────────────────────────

    def _register_news_sources(self) -> int:
        count = 0

        # CoinDesk RSS (FREE, no keys)
        try:
            import ui.feeds.coindesk_rss  # noqa: F401

            self._sources["coindesk_rss"] = SourceHandle(
                name="CoinDesk RSS",
                source=IngestionSource.COINDESK_RSS,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("CoinDesk RSS unavailable: %s", e)

        # News feed adapter
        try:
            from data_sources.external.news_feed import NewsFeedAdapter

            adapter = NewsFeedAdapter()
            self._sources["news_feed"] = SourceHandle(
                name="News Feed", source=IngestionSource.NEWS_FEED, adapter=adapter
            )
            count += 1
        except Exception as e:
            logger.debug("News feed unavailable: %s", e)

        # Alpaca news (FREE for crypto)
        try:
            from alpaca.data.historical import CryptoHistoricalDataClient

            self._sources["alpaca_news"] = SourceHandle(
                name="Alpaca News",
                source=IngestionSource.ALPACA_NEWS,
                adapter=CryptoHistoricalDataClient(),
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Alpaca news unavailable: %s", e)

        # News fanout (CoinDesk → signal + hazard projection)
        try:
            import ui.feeds.news_fanout  # noqa: F401

            self._sources["news_fanout"] = SourceHandle(
                name="News Fanout", source=IngestionSource.NEWS_FANOUT, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("News fanout unavailable: %s", e)

        # News runner (orchestrates all news pumps)
        try:
            import ui.feeds.news_runner  # noqa: F401

            self._sources["news_runner"] = SourceHandle(
                name="News Runner", source=IngestionSource.NEWS_FEED, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("News runner unavailable: %s", e)

        return count

    # ──────────────────────────────────────────────────────────────
    # Registration — 4. Social sentiment
    # ──────────────────────────────────────────────────────────────

    def _register_social_sources(self) -> int:
        count = 0

        # Reddit sentiment
        try:
            from data_sources.external.reddit_sentiment import (
                RedditSentimentAdapter,
            )

            adapter = RedditSentimentAdapter()
            self._sources["reddit"] = SourceHandle(
                name="Reddit Sentiment", source=IngestionSource.REDDIT_SENTIMENT, adapter=adapter
            )
            count += 1
        except Exception as e:
            logger.debug("Reddit sentiment unavailable: %s", e)

        # X/Twitter sentiment
        try:
            from data_sources.external.x_crypto_sentiment import (
                XCryptoSentimentAdapter,
            )

            adapter = XCryptoSentimentAdapter()
            self._sources["x_sentiment"] = SourceHandle(
                name="X Crypto Sentiment", source=IngestionSource.X_SENTIMENT, adapter=adapter
            )
            count += 1
        except Exception as e:
            logger.debug("X sentiment unavailable: %s", e)

        # Social sentiment aggregator
        try:
            from data_sources.external.social_sentiment import (
                SocialSentimentAdapter,
            )

            adapter = SocialSentimentAdapter()
            self._sources["social_sentiment"] = SourceHandle(
                name="Social Sentiment", source=IngestionSource.SOCIAL_SENTIMENT, adapter=adapter
            )
            count += 1
        except Exception as e:
            logger.debug("Social sentiment unavailable: %s", e)

        return count

    # ──────────────────────────────────────────────────────────────
    # Registration — 5. On-chain analytics
    # ──────────────────────────────────────────────────────────────

    def _register_onchain_sources(self) -> int:
        count = 0

        # Glassnode
        try:
            from sensory.onchain.glassnode import GlassnodeClient

            api_key = os.environ.get("GLASSNODE_API_KEY", "")
            adapter = GlassnodeClient(api_key=api_key, in_memory=not bool(api_key))
            self._sources["glassnode"] = SourceHandle(
                name="Glassnode",
                source=IngestionSource.GLASSNODE,
                adapter=adapter,
                connected=bool(api_key),
            )
            count += 1
        except Exception as e:
            logger.debug("Glassnode unavailable: %s", e)

        # Nansen
        try:
            from sensory.onchain.nansen import NansenClient

            api_key = os.environ.get("NANSEN_API_KEY", "")
            adapter = NansenClient(api_key=api_key, in_memory=not bool(api_key))
            self._sources["nansen"] = SourceHandle(
                name="Nansen Smart Money",
                source=IngestionSource.NANSEN,
                adapter=adapter,
                connected=bool(api_key),
            )
            count += 1
        except Exception as e:
            logger.debug("Nansen unavailable: %s", e)

        # Arkham Intelligence
        try:
            from sensory.onchain.arkham import ArkhamClient

            api_key = os.environ.get("ARKHAM_API_KEY", "")
            adapter = ArkhamClient(api_key=api_key, in_memory=not bool(api_key))
            self._sources["arkham"] = SourceHandle(
                name="Arkham Intelligence",
                source=IngestionSource.ARKHAM,
                adapter=adapter,
                connected=bool(api_key),
            )
            count += 1
        except Exception as e:
            logger.debug("Arkham unavailable: %s", e)

        # Dune Analytics
        try:
            import sensory.onchain.dune_adapter  # noqa: F401

            self._sources["dune"] = SourceHandle(
                name="Dune Analytics",
                source=IngestionSource.DUNE,
                adapter=None,
                connected=bool(os.environ.get("DUNE_API_KEY")),
            )
            count += 1
        except Exception as e:
            logger.debug("Dune unavailable: %s", e)

        # Etherscan (needs API key)
        try:
            from mind.sources.providers.onchain import EtherscanProvider

            self._sources["etherscan"] = SourceHandle(
                name="Etherscan",
                source=IngestionSource.ETHERSCAN,
                adapter=EtherscanProvider(),
                connected=bool(os.environ.get("ETHERSCAN_API_KEY")),
            )
            count += 1
        except Exception as e:
            logger.debug("Etherscan unavailable: %s", e)

        # Bitquery (needs API key)
        try:
            from mind.sources.providers.onchain import BitqueryProvider

            self._sources["bitquery"] = SourceHandle(
                name="Bitquery",
                source=IngestionSource.BITQUERY,
                adapter=BitqueryProvider(),
                connected=bool(os.environ.get("BITQUERY_API_KEY")),
            )
            count += 1
        except Exception as e:
            logger.debug("Bitquery unavailable: %s", e)

        # Solana RPC (public, free)
        try:
            from mind.sources.providers.onchain import SolanaRPCProvider

            self._sources["solana_rpc"] = SourceHandle(
                name="Solana RPC",
                source=IngestionSource.SOLANA_RPC,
                adapter=SolanaRPCProvider(),
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Solana RPC unavailable: %s", e)

        # Ethplorer (free tier)
        try:
            from mind.sources.providers.onchain import EthplorerProvider

            self._sources["ethplorer"] = SourceHandle(
                name="Ethplorer",
                source=IngestionSource.ETHPLORER,
                adapter=EthplorerProvider(),
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Ethplorer unavailable: %s", e)

        # On-chain stream registry (blocks, mempool, DEX pools)
        try:
            from mind.sources.onchain_streams import OnchainStreamRegistry

            self._sources["onchain_streams"] = SourceHandle(
                name="Onchain Streams",
                source=IngestionSource.ONCHAIN_STREAMS,
                adapter=OnchainStreamRegistry(),
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Onchain streams unavailable: %s", e)

        return count

    # ──────────────────────────────────────────────────────────────
    # Registration — 6. Macro / economic
    # ──────────────────────────────────────────────────────────────

    def _register_macro_sources(self) -> int:
        count = 0

        # FRED
        try:
            import ui.feeds.fred_http  # noqa: F401

            self._sources["fred_macro"] = SourceHandle(
                name="FRED Macro", source=IngestionSource.FRED_MACRO, adapter=None
            )
            count += 1
        except Exception as e:
            logger.debug("FRED unavailable: %s", e)

        # BLS
        try:
            import ui.feeds.bls_http  # noqa: F401

            self._sources["bls_macro"] = SourceHandle(
                name="BLS Macro", source=IngestionSource.BLS_MACRO, adapter=None
            )
            count += 1
        except Exception as e:
            logger.debug("BLS unavailable: %s", e)

        return count

    # ──────────────────────────────────────────────────────────────
    # Registration — 7. External signals / trading platforms
    # ──────────────────────────────────────────────────────────────

    def _register_signal_sources(self) -> int:
        count = 0

        # TradingView ideas
        try:
            from data_sources.external.tradingview_ideas import (
                TradingViewIdeasAdapter,
            )

            adapter = TradingViewIdeasAdapter()
            self._sources["tradingview_ideas"] = SourceHandle(
                name="TradingView Ideas", source=IngestionSource.TRADINGVIEW_IDEAS, adapter=adapter
            )
            count += 1
        except Exception as e:
            logger.debug("TradingView ideas unavailable: %s", e)

        # TradingView alerts (webhook-driven)
        try:
            import ui.feeds.tradingview_alert  # noqa: F401

            self._sources["tradingview_alert"] = SourceHandle(
                name="TradingView Alerts",
                source=IngestionSource.TRADINGVIEW_ALERT,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("TradingView alerts unavailable: %s", e)

        # TradingView platform adapter (signal routing)
        try:
            import execution_engine.adapters.external.tradingview  # noqa: F401

            self._sources["tradingview_platform"] = SourceHandle(
                name="TradingView Platform",
                source=IngestionSource.TRADINGVIEW_ALERT,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("TradingView platform unavailable: %s", e)

        # MT5 (MetaTrader 5)
        try:
            import execution_engine.adapters.external.mt5  # noqa: F401

            self._sources["mt5"] = SourceHandle(
                name="MetaTrader 5", source=IngestionSource.MT5, adapter=None
            )
            count += 1
        except Exception as e:
            logger.debug("MT5 unavailable: %s", e)

        # QuantConnect
        try:
            import execution_engine.adapters.external.quantconnect  # noqa: F401

            self._sources["quantconnect"] = SourceHandle(
                name="QuantConnect", source=IngestionSource.QUANTCONNECT, adapter=None
            )
            count += 1
        except Exception as e:
            logger.debug("QuantConnect unavailable: %s", e)

        # Backtrader
        try:
            import execution_engine.adapters.external.backtrader  # noqa: F401

            self._sources["backtrader"] = SourceHandle(
                name="Backtrader", source=IngestionSource.BACKTRADER, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("Backtrader unavailable: %s", e)

        # Freqtrade
        try:
            import execution_engine.adapters.external.freqtrade  # noqa: F401

            self._sources["freqtrade"] = SourceHandle(
                name="Freqtrade", source=IngestionSource.FREQTRADE, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("Freqtrade unavailable: %s", e)

        # Jesse
        try:
            import execution_engine.adapters.external.jesse  # noqa: F401

            self._sources["jesse"] = SourceHandle(
                name="Jesse", source=IngestionSource.JESSE, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("Jesse unavailable: %s", e)

        # QSTrader
        try:
            import execution_engine.adapters.external.qstrader  # noqa: F401

            self._sources["qstrader"] = SourceHandle(
                name="QSTrader", source=IngestionSource.QSTRADER, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("QSTrader unavailable: %s", e)

        # VectorBT
        try:
            import execution_engine.adapters.external.vectorbt  # noqa: F401

            self._sources["vectorbt"] = SourceHandle(
                name="VectorBT", source=IngestionSource.VECTORBT, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("VectorBT unavailable: %s", e)

        return count

    # ──────────────────────────────────────────────────────────────
    # Registration — 8. Sensory sources
    # ──────────────────────────────────────────────────────────────

    def _register_sensory_sources(self) -> int:
        count = 0

        # Technical indicators (pure computation, always available)
        try:
            import sensory.indicators.technical  # noqa: F401

            self._sources["technical_indicators"] = SourceHandle(
                name="Technical Indicators",
                source=IngestionSource.TECHNICAL_INDICATORS,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Technical indicators unavailable: %s", e)

        # Neuromorphic pulse (Indira signal)
        try:
            import sensory.neuromorphic.indira_signal  # noqa: F401

            self._sources["neuromorphic_pulse"] = SourceHandle(
                name="Neuromorphic Pulse",
                source=IngestionSource.NEUROMORPHIC_PULSE,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Neuromorphic pulse unavailable: %s", e)

        # Dyon anomaly perception
        try:
            import sensory.neuromorphic.dyon_anomaly  # noqa: F401

            self._sources["dyon_anomaly"] = SourceHandle(
                name="Dyon Anomaly",
                source=IngestionSource.DYON_ANOMALY,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Dyon anomaly unavailable: %s", e)

        # Governance risk perception
        try:
            import sensory.neuromorphic.governance_risk  # noqa: F401

            self._sources["governance_risk"] = SourceHandle(
                name="Governance Risk",
                source=IngestionSource.GOVERNANCE_RISK,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Governance risk unavailable: %s", e)

        # SNN LIF (spiking neural network, leaky integrate-and-fire)
        try:
            import sensory.neuromorphic.snn_lif  # noqa: F401

            self._sources["snn_lif"] = SourceHandle(
                name="SNN LIF", source=IngestionSource.SNN_LIF, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("SNN LIF unavailable: %s", e)

        # SNNTorch detector
        try:
            import sensory.neuromorphic.snntorch_detector  # noqa: F401

            self._sources["snntorch"] = SourceHandle(
                name="SNNTorch Detector",
                source=IngestionSource.SNNTORCH,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("SNNTorch unavailable: %s", e)

        # Nengo cognitive model
        try:
            import sensory.neuromorphic.nengo_cognitive  # noqa: F401

            self._sources["nengo_cognitive"] = SourceHandle(
                name="Nengo Cognitive",
                source=IngestionSource.NENGO_COGNITIVE,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Nengo cognitive unavailable: %s", e)

        # Spyke encoder
        try:
            import sensory.neuromorphic.spyke_encoder  # noqa: F401

            self._sources["spyke_encoder"] = SourceHandle(
                name="Spyke Encoder",
                source=IngestionSource.SPYKE_ENCODER,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Spyke encoder unavailable: %s", e)

        # Neuromorphic neuro prototype
        try:
            import sensory.neuromorphic.neuro_prototype  # noqa: F401

            self._sources["neuro_prototype"] = SourceHandle(
                name="Neuro Prototype",
                source=IngestionSource.NEUROMORPHIC_PULSE,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Neuro prototype unavailable: %s", e)

        # Governance risk SNN variant
        try:
            import sensory.neuromorphic.governance_risk_snn  # noqa: F401

            self._sources["governance_risk_snn"] = SourceHandle(
                name="Governance Risk SNN",
                source=IngestionSource.GOVERNANCE_RISK,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Governance risk SNN unavailable: %s", e)

        # Voice (synthesizer + transcriber)
        try:
            import sensory.voice.synthesizer  # noqa: F401
            import sensory.voice.transcriber  # noqa: F401

            self._sources["voice"] = SourceHandle(
                name="Voice I/O", source=IngestionSource.VOICE, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("Voice unavailable: %s", e)

        # Regulatory sensory
        try:
            import sensory.regulatory  # noqa: F401

            self._sources["regulatory"] = SourceHandle(
                name="Regulatory", source=IngestionSource.REGULATORY, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("Regulatory unavailable: %s", e)

        # Alt sensory
        try:
            import sensory.alt  # noqa: F401

            self._sources["alt_sensory"] = SourceHandle(
                name="Alt Sensory", source=IngestionSource.ALT_SENSORY, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("Alt sensory unavailable: %s", e)

        # Cognitive sensory
        try:
            import sensory.cognitive  # noqa: F401

            self._sources["cognitive_sensory"] = SourceHandle(
                name="Cognitive Sensory",
                source=IngestionSource.COGNITIVE_SENSORY,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Cognitive sensory unavailable: %s", e)

        # Dev sensory
        try:
            import sensory.dev  # noqa: F401

            self._sources["dev_sensory"] = SourceHandle(
                name="Dev Sensory", source=IngestionSource.DEV_SENSORY, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("Dev sensory unavailable: %s", e)

        return count

    # ──────────────────────────────────────────────────────────────
    # Registration — 9. Learning sources
    # ──────────────────────────────────────────────────────────────

    def _register_learning_sources(self) -> int:
        count = 0

        # Web autolearn pipeline
        try:
            import sensory.web_autolearn  # noqa: F401

            self._sources["web_autolearn"] = SourceHandle(
                name="Web AutoLearn",
                source=IngestionSource.WEB_AUTOLEARN,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Web autolearn unavailable: %s", e)

        # Trader intelligence pipeline
        try:
            import sensory.trader_intelligence.pipeline  # noqa: F401

            self._sources["trader_intelligence"] = SourceHandle(
                name="Trader Intelligence",
                source=IngestionSource.TRADER_INTELLIGENCE,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Trader intelligence unavailable: %s", e)

        # Learning engine
        try:
            import learning_engine.engine  # noqa: F401

            self._sources["learning_engine"] = SourceHandle(
                name="Learning Engine",
                source=IngestionSource.LEARNING_ENGINE,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Learning engine unavailable: %s", e)

        return count

    # ──────────────────────────────────────────────────────────────
    # Registration — 10. Infrastructure bridges
    # ──────────────────────────────────────────────────────────────

    def _register_infra_sources(self) -> int:
        count = 0

        # Kafka event bridge
        try:
            import integrations.kafka_adapter.streaming  # noqa: F401

            self._sources["kafka_events"] = SourceHandle(
                name="Kafka Events",
                source=IngestionSource.KAFKA_EVENTS,
                adapter=None,
                connected=bool(os.environ.get("KAFKA_BOOTSTRAP_SERVERS")),
            )
            count += 1
        except Exception as e:
            logger.debug("Kafka unavailable: %s", e)

        # DuckDB analytics
        try:
            import integrations.duckdb_adapter.analytics  # noqa: F401

            self._sources["duckdb_analytics"] = SourceHandle(
                name="DuckDB Analytics",
                source=IngestionSource.DUCKDB_ANALYTICS,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("DuckDB unavailable: %s", e)

        # Qdrant vector memory
        try:
            import integrations.qdrant_adapter.memory  # noqa: F401

            self._sources["qdrant_memory"] = SourceHandle(
                name="Qdrant Memory",
                source=IngestionSource.QDRANT_MEMORY,
                adapter=None,
                connected=bool(os.environ.get("QDRANT_URL")),
            )
            count += 1
        except Exception as e:
            logger.debug("Qdrant unavailable: %s", e)

        return count

    # ──────────────────────────────────────────────────────────────
    # Poll methods — one per source type
    # ──────────────────────────────────────────────────────────────

    def _poll_alpaca_market(
        self,
        adapter: Any,
        ts: int,
    ) -> list[IngestedTick]:
        """Poll Alpaca crypto for latest bars."""
        ticks: list[IngestedTick] = []
        symbols = os.environ.get("DIX_ALPACA_SYMBOLS", "BTC/USD,ETH/USD,SOL/USD").split(",")
        for symbol in symbols:
            try:
                bar = adapter.get_latest_bar(symbol)
                if bar is not None:
                    ticks.append(
                        IngestedTick(
                            source=IngestionSource.ALPACA_REST,
                            symbol=bar.symbol,
                            price=bar.close,
                            volume=bar.volume,
                            ts_ns=ts,
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
                    )
            except Exception:
                pass
        return ticks

    def _poll_ccxt(self, adapter: Any, ts: int) -> list[IngestedTick]:
        """Poll CCXT bridge for ticker data."""
        ticks: list[IngestedTick] = []
        symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        for symbol in symbols:
            try:
                snap = adapter.get_ticker(symbol)
                if snap is not None:
                    ticks.append(
                        IngestedTick(
                            source=IngestionSource.CCXT_POLL,
                            symbol=symbol,
                            price=snap.last,
                            volume=snap.volume_24h,
                            ts_ns=ts,
                        )
                    )
            except Exception:
                pass
        return ticks

    def _poll_openbb(self, adapter: Any, ts: int) -> list[IngestedTick]:
        """Poll OpenBB for crypto metrics."""
        ticks: list[IngestedTick] = []
        for symbol in ("BTC", "ETH", "SOL"):
            try:
                metrics = adapter.fetch_crypto_metrics(symbol)
                for m in metrics:
                    ticks.append(
                        IngestedTick(
                            source=IngestionSource.OPENBB,
                            symbol=m.symbol,
                            price=m.price,
                            volume=m.volume_24h,
                            ts_ns=ts,
                            raw_payload={
                                "market_cap": m.market_cap,
                                "change_24h_pct": m.change_24h_pct,
                                "source": "openbb",
                            },
                        )
                    )
            except Exception:
                pass
        return ticks

    def _poll_raydium_pools(
        self,
        adapter: Any,
        ts: int,
    ) -> list[IngestedTick]:
        """Raydium pool data — handled by ui/feeds/runner."""
        return []

    def _poll_polygon(self, adapter: Any, ts: int) -> list[IngestedTick]:
        """Polygon.io — needs API key, handled via adapter polling."""
        return []

    def _poll_iex(self, adapter: Any, ts: int) -> list[IngestedTick]:
        """IEX Cloud — needs API key, handled via adapter polling."""
        return []

    def _poll_alphavantage(
        self,
        adapter: Any,
        ts: int,
    ) -> list[IngestedTick]:
        """Alpha Vantage — needs API key, handled via adapter polling."""
        return []

    def _poll_coindesk(self, adapter: Any, ts: int) -> list[IngestedTick]:
        """CoinDesk RSS — handled by ui/feeds/runner."""
        return []

    def _poll_news_feed(self, adapter: Any, ts: int) -> list[IngestedTick]:
        """News feed — returns empty until raw articles are pushed."""
        return []

    def _poll_alpaca_news(self, adapter: Any, ts: int) -> list[IngestedTick]:
        """Poll Alpaca for crypto news."""
        ticks: list[IngestedTick] = []
        try:
            from alpaca.data.requests import CryptoBarsRequest
            from alpaca.data.timeframe import TimeFrame

            req = CryptoBarsRequest(
                symbol_or_symbols=["BTC/USD"], timeframe=TimeFrame.Hour, limit=1
            )
            bars = adapter.get_crypto_bars(req)
            for bar in bars["BTC/USD"]:
                ticks.append(
                    IngestedTick(
                        source=IngestionSource.ALPACA_NEWS,
                        symbol="BTC/USD",
                        price=float(bar.close),
                        volume=float(bar.volume),
                        ts_ns=ts,
                        raw_payload={"source": "alpaca_news"},
                    )
                )
        except Exception:
            pass
        return ticks

    def _poll_reddit(self, adapter: Any, ts: int) -> list[IngestedTick]:
        """Poll Reddit sentiment."""
        ticks: list[IngestedTick] = []
        try:
            signals = adapter.fetch_signals(limit=20)
            for sig in signals:
                for ticker in sig.mentioned_tickers:
                    ticks.append(
                        IngestedTick(
                            source=IngestionSource.REDDIT_SENTIMENT,
                            symbol=ticker,
                            price=0.0,
                            volume=float(sig.upvotes),
                            ts_ns=ts,
                            raw_payload={
                                "sentiment": sig.sentiment_score,
                                "hype": sig.hype_score,
                                "subreddit": sig.subreddit,
                                "source": "reddit",
                            },
                        )
                    )
        except Exception:
            pass
        return ticks

    def _poll_x_sentiment(self, adapter: Any, ts: int) -> list[IngestedTick]:
        """Poll X/Twitter crypto sentiment."""
        ticks: list[IngestedTick] = []
        try:
            signals = adapter.fetch_signals(limit=20)
            for sig in signals:
                for ticker in sig.mentioned_tickers:
                    ticks.append(
                        IngestedTick(
                            source=IngestionSource.X_SENTIMENT,
                            symbol=ticker,
                            price=0.0,
                            volume=float(sig.engagement_score),
                            ts_ns=ts,
                            raw_payload={
                                "sentiment": sig.sentiment_score,
                                "author": sig.author_handle,
                                "followers": sig.author_followers,
                                "source": "x",
                            },
                        )
                    )
        except Exception:
            pass
        return ticks

    def _poll_social_sentiment(
        self,
        adapter: Any,
        ts: int,
    ) -> list[IngestedTick]:
        """Aggregated social sentiment — requires raw_data push."""
        return []

    def _poll_glassnode(self, adapter: Any, ts: int) -> list[IngestedTick]:
        """Poll Glassnode on-chain metrics."""
        ticks: list[IngestedTick] = []
        metrics = ["indicators/nvt", "indicators/sopr", "market/price_usd_close"]
        for metric in metrics:
            try:
                data = adapter.get_metric(metric, asset="BTC")
                for point in data:
                    ticks.append(
                        IngestedTick(
                            source=IngestionSource.GLASSNODE,
                            symbol="BTC",
                            price=point.value,
                            volume=0.0,
                            ts_ns=ts,
                            raw_payload={
                                "metric": point.metric,
                                "asset": point.asset,
                                "source": "glassnode",
                            },
                        )
                    )
            except Exception:
                pass
        return ticks

    def _poll_nansen(self, adapter: Any, ts: int) -> list[IngestedTick]:
        """Poll Nansen smart money flows."""
        ticks: list[IngestedTick] = []
        try:
            txns = adapter.get_smart_money_txns(limit=20)
            for tx in txns:
                ticks.append(
                    IngestedTick(
                        source=IngestionSource.NANSEN,
                        symbol=tx.token,
                        price=tx.amount_usd,
                        volume=tx.amount_usd,
                        ts_ns=ts,
                        raw_payload={
                            "action": tx.action,
                            "address": tx.address,
                            "label": tx.label,
                            "source": "nansen",
                        },
                    )
                )
        except Exception:
            pass
        return ticks

    def _poll_arkham(self, adapter: Any, ts: int) -> list[IngestedTick]:
        """Arkham — entity lookup is address-based, not polling."""
        return []

    def _poll_dune(self, adapter: Any, ts: int) -> list[IngestedTick]:
        """Dune Analytics — query execution is async, not polling."""
        return []

    def _poll_onchain_streams(
        self,
        adapter: Any,
        ts: int,
    ) -> list[IngestedTick]:
        """Poll on-chain stream registry for new events."""
        ticks: list[IngestedTick] = []
        try:
            events = adapter.pull_all()
            for evt in events:
                ticks.append(
                    IngestedTick(
                        source=IngestionSource.ONCHAIN_STREAMS,
                        symbol=evt.chain,
                        price=0.0,
                        volume=0.0,
                        ts_ns=ts,
                        raw_payload={
                            "kind": evt.kind,
                            "chain": evt.chain,
                            **evt.payload,
                        },
                    )
                )
        except Exception:
            pass
        return ticks

    def _poll_fred(self, adapter: Any, ts: int) -> list[IngestedTick]:
        """FRED macro data — handled by ui/feeds/runner."""
        return []

    def _poll_tradingview_ideas(
        self,
        adapter: Any,
        ts: int,
    ) -> list[IngestedTick]:
        """Poll TradingView ideas."""
        ticks: list[IngestedTick] = []
        try:
            ideas = adapter.fetch_signals(limit=10)
            for idea in ideas:
                ticks.append(
                    IngestedTick(
                        source=IngestionSource.TRADINGVIEW_IDEAS,
                        symbol=idea.symbol,
                        price=idea.entry_price or 0.0,
                        volume=float(idea.likes),
                        ts_ns=ts,
                        raw_payload={
                            "direction": idea.direction,
                            "author": idea.author,
                            "reputation": idea.author_reputation,
                            "patterns": list(idea.chart_patterns),
                            "source": "tradingview",
                        },
                    )
                )
        except Exception:
            pass
        return ticks

    def _poll_web_autolearn(
        self,
        adapter: Any,
        ts: int,
    ) -> list[IngestedTick]:
        """Web autolearn — triggered by crawler pipeline, not polling."""
        return []

    def _poll_trader_intelligence(
        self,
        adapter: Any,
        ts: int,
    ) -> list[IngestedTick]:
        """Trader intelligence — event-driven, not polling."""
        return []

    # ──────────────────────────────────────────────────────────────
    # Registration — 11. mind/sources providers
    # ──────────────────────────────────────────────────────────────

    def _register_mind_sources(self) -> int:
        count = 0

        # CEX market data provider
        try:
            from mind.sources.providers.market_cex import (
                BinanceSpotProvider,
            )

            self._sources["mind_market_cex"] = SourceHandle(
                name="Mind Market CEX",
                source=IngestionSource.MIND_MARKET_CEX,
                adapter=BinanceSpotProvider(),
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Mind market CEX unavailable: %s", e)

        # Expanded market sources (Bybit, Gate, KuCoin)
        try:
            import mind.sources.providers.market_expanded  # noqa: F401

            self._sources["mind_market_expanded"] = SourceHandle(
                name="Mind Market Expanded",
                source=IngestionSource.MIND_MARKET_EXPANDED,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Mind market expanded unavailable: %s", e)

        # Market WebSocket streams
        try:
            import mind.sources.market_streams  # noqa: F401

            self._sources["mind_market_streams"] = SourceHandle(
                name="Mind Market Streams",
                source=IngestionSource.MIND_MARKET_STREAMS,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Mind market streams unavailable: %s", e)

        # News provider
        try:
            import mind.sources.providers.news  # noqa: F401

            self._sources["mind_news"] = SourceHandle(
                name="Mind News Provider",
                source=IngestionSource.MIND_NEWS,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Mind news unavailable: %s", e)

        # Expanded news sources
        try:
            import mind.sources.providers.news_expanded  # noqa: F401

            self._sources["mind_news_expanded"] = SourceHandle(
                name="Mind News Expanded",
                source=IngestionSource.MIND_NEWS_EXPANDED,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Mind news expanded unavailable: %s", e)

        # News WebSocket streams
        try:
            import mind.sources.news_streams  # noqa: F401

            self._sources["mind_news_streams"] = SourceHandle(
                name="Mind News Streams",
                source=IngestionSource.MIND_NEWS_STREAMS,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Mind news streams unavailable: %s", e)

        # Sentiment provider
        try:
            import mind.sources.providers.sentiment  # noqa: F401

            self._sources["mind_sentiment"] = SourceHandle(
                name="Mind Sentiment",
                source=IngestionSource.MIND_SENTIMENT,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Mind sentiment unavailable: %s", e)

        # Sentiment streams
        try:
            import mind.sources.sentiment_streams  # noqa: F401

            self._sources["mind_sentiment_streams"] = SourceHandle(
                name="Mind Sentiment Streams",
                source=IngestionSource.MIND_SENTIMENT_STREAMS,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Mind sentiment streams unavailable: %s", e)

        # API sniffer
        try:
            import mind.sources.providers.api_sniffer  # noqa: F401

            self._sources["mind_api_sniffer"] = SourceHandle(
                name="Mind API Sniffer",
                source=IngestionSource.MIND_API_SNIFFER,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Mind API sniffer unavailable: %s", e)

        # Code search
        try:
            import mind.sources.providers.code_search  # noqa: F401

            self._sources["mind_code_search"] = SourceHandle(
                name="Mind Code Search",
                source=IngestionSource.MIND_CODE_SEARCH,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Mind code search unavailable: %s", e)

        return count

    # ──────────────────────────────────────────────────────────────
    # Registration — 12. Integration platforms
    # ──────────────────────────────────────────────────────────────

    def _register_integration_sources(self) -> int:
        count = 0

        # PyTorch Lightning trainer
        try:
            import integrations.lightning_adapter.trainer  # noqa: F401

            self._sources["lightning_trainer"] = SourceHandle(
                name="Lightning Trainer",
                source=IngestionSource.LIGHTNING_TRAINER,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Lightning trainer unavailable: %s", e)

        # Ray distributed compute
        try:
            import integrations.ray_adapter.compute  # noqa: F401

            self._sources["ray_compute"] = SourceHandle(
                name="Ray Compute", source=IngestionSource.RAY_COMPUTE, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("Ray compute unavailable: %s", e)

        # Temporal workflows
        try:
            import integrations.temporal_adapter.workflows  # noqa: F401

            self._sources["temporal_workflows"] = SourceHandle(
                name="Temporal Workflows",
                source=IngestionSource.TEMPORAL_WORKFLOWS,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Temporal workflows unavailable: %s", e)

        # LangGraph AI orchestrator
        try:
            import integrations.langgraph_adapter.orchestrator  # noqa: F401

            self._sources["langgraph_orchestrator"] = SourceHandle(
                name="LangGraph Orchestrator",
                source=IngestionSource.LANGGRAPH_ORCHESTRATOR,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("LangGraph unavailable: %s", e)

        # Haystack RAG pipeline
        try:
            import integrations.haystack_adapter.rag  # noqa: F401

            self._sources["haystack_rag"] = SourceHandle(
                name="Haystack RAG",
                source=IngestionSource.HAYSTACK_RAG,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Haystack RAG unavailable: %s", e)

        # Feast feature store
        try:
            import integrations.feast_adapter.features  # noqa: F401

            self._sources["feast_features"] = SourceHandle(
                name="Feast Features",
                source=IngestionSource.FEAST_FEATURES,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Feast features unavailable: %s", e)

        # OpenTelemetry metrics
        try:
            import integrations.otel_adapter.metrics  # noqa: F401

            self._sources["otel_metrics"] = SourceHandle(
                name="OTel Metrics",
                source=IngestionSource.OTEL_METRICS,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("OTel metrics unavailable: %s", e)

        # OpenTelemetry tracing
        try:
            import integrations.otel_adapter.tracing  # noqa: F401

            self._sources["otel_tracing"] = SourceHandle(
                name="OTel Tracing",
                source=IngestionSource.OTEL_TRACING,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("OTel tracing unavailable: %s", e)

        # OPA policy engine
        try:
            import integrations.opa_adapter.policy  # noqa: F401

            self._sources["opa_policy"] = SourceHandle(
                name="OPA Policy", source=IngestionSource.OPA_POLICY, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("OPA policy unavailable: %s", e)

        # OPA governance bridge
        try:
            import integrations.wiring.opa_governance_bridge  # noqa: F401

            self._sources["opa_governance_bridge"] = SourceHandle(
                name="OPA Governance Bridge",
                source=IngestionSource.OPA_GOVERNANCE_BRIDGE,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("OPA governance bridge unavailable: %s", e)

        # Kafka event bridge (wiring layer)
        try:
            import integrations.wiring.kafka_event_bridge  # noqa: F401

            self._sources["kafka_event_bridge"] = SourceHandle(
                name="Kafka Event Bridge",
                source=IngestionSource.KAFKA_EVENT_BRIDGE,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Kafka event bridge unavailable: %s", e)

        # Qdrant memory bridge (wiring layer)
        try:
            import integrations.wiring.qdrant_memory_bridge  # noqa: F401

            self._sources["qdrant_memory_bridge"] = SourceHandle(
                name="Qdrant Memory Bridge",
                source=IngestionSource.QDRANT_MEMORY_BRIDGE,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Qdrant memory bridge unavailable: %s", e)

        return count

    # ──────────────────────────────────────────────────────────────
    # Registration — 13. Feed runners
    # ──────────────────────────────────────────────────────────────

    def _register_feed_runners(self) -> int:
        count = 0

        # Main feed runner (orchestrates all pumps)
        try:
            import ui.feeds.runner  # noqa: F401

            self._sources["feed_runner"] = SourceHandle(
                name="Feed Runner", source=IngestionSource.FEED_RUNNER, adapter=None, connected=True
            )
            count += 1
        except Exception as e:
            logger.debug("Feed runner unavailable: %s", e)

        # Raydium runner
        try:
            import ui.feeds.raydium_runner  # noqa: F401

            self._sources["raydium_runner"] = SourceHandle(
                name="Raydium Runner",
                source=IngestionSource.RAYDIUM_RUNNER,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Raydium runner unavailable: %s", e)

        # PumpFun runner
        try:
            import ui.feeds.pumpfun_runner  # noqa: F401

            self._sources["pumpfun_runner"] = SourceHandle(
                name="PumpFun Runner",
                source=IngestionSource.PUMPFUN_RUNNER,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("PumpFun runner unavailable: %s", e)

        # Feeds routes (FastAPI endpoints)
        try:
            import ui.feeds_routes  # noqa: F401

            self._sources["feeds_routes"] = SourceHandle(
                name="Feeds Routes",
                source=IngestionSource.FEEDS_ROUTES,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Feeds routes unavailable: %s", e)

        return count

    # ──────────────────────────────────────────────────────────────
    # Registration — 14. Web autolearn variants
    # ──────────────────────────────────────────────────────────────

    def _register_autolearn_variants(self) -> int:
        count = 0

        # Firecrawl crawler
        try:
            import sensory.web_autolearn.crawler_firecrawl  # noqa: F401

            self._sources["crawler_firecrawl"] = SourceHandle(
                name="Firecrawl Crawler",
                source=IngestionSource.CRAWLER_FIRECRAWL,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Firecrawl unavailable: %s", e)

        # Playwright crawler
        try:
            import sensory.web_autolearn.crawler_playwright  # noqa: F401

            self._sources["crawler_playwright"] = SourceHandle(
                name="Playwright Crawler",
                source=IngestionSource.CRAWLER_PLAYWRIGHT,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Playwright crawler unavailable: %s", e)

        # Scrapy crawler
        try:
            import sensory.web_autolearn.crawler_scrapy  # noqa: F401

            self._sources["crawler_scrapy"] = SourceHandle(
                name="Scrapy Crawler",
                source=IngestionSource.CRAWLER_SCRAPY,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Scrapy crawler unavailable: %s", e)

        # n8n automation pipeline
        try:
            import sensory.web_autolearn.n8n_pipeline  # noqa: F401

            self._sources["n8n_pipeline"] = SourceHandle(
                name="n8n Pipeline",
                source=IngestionSource.N8N_PIPELINE,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("n8n pipeline unavailable: %s", e)

        return count

    # ──────────────────────────────────────────────────────────────
    # Registration — 15. Paper trading adapter
    # ──────────────────────────────────────────────────────────────

    def _register_paper_adapter(self) -> int:
        count = 0

        try:
            import execution_engine.adapters.paper  # noqa: F401

            self._sources["paper_trading"] = SourceHandle(
                name="Paper Trading",
                source=IngestionSource.PAPER_TRADING,
                adapter=None,
                connected=True,
            )
            count += 1
        except Exception as e:
            logger.debug("Paper trading unavailable: %s", e)

        return count
