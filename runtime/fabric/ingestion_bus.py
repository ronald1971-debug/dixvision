"""Ingestion Bus — unified market data ingestion (CONVERGENCE PILLAR 2).

All market data enters the system through this bus:
- WebSocket feeds (Binance, Raydium, PumpFun)
- REST polling (AlphaVantage, Polygon, IEX)
- External signals (TradingView alerts, MT5)

The bus normalizes all data into canonical MarketTick / SignalEvent and
updates the RuntimeAuthority with the latest market state.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum, auto

from runtime.authority import RuntimeAuthorityStore, WriterToken


class IngestionSource(StrEnum):
    """Known ingestion sources — every data feed in the system."""

    # ── Exchange WebSocket streams ──
    BINANCE_WS = auto()
    BINANCE_USER_WS = auto()
    RAYDIUM_WS = auto()
    PUMPFUN_WS = auto()

    # ── REST / SDK polling ──
    REST_POLL = auto()
    ALPACA_REST = auto()
    ALPACA_WS = auto()
    CCXT_POLL = auto()
    OPENBB = auto()
    RAYDIUM_POOLS = auto()

    # ── Market data providers ──
    POLYGON = auto()
    IEX_CLOUD = auto()
    ALPHAVANTAGE = auto()

    # ── Execution adapters (fill/balance events) ──
    ALPACA_TRADING = auto()
    IBKR = auto()
    HUMMINGBOT = auto()
    UNISWAPX = auto()
    VNPY = auto()
    SOLANA_NATIVE = auto()
    HELIUS = auto()
    PUMPFUN_EXEC = auto()

    # ── External signals ──
    EXTERNAL_SIGNAL = auto()
    TRADINGVIEW_ALERT = auto()
    TRADINGVIEW_IDEAS = auto()

    # ── External trading platforms ──
    MT5 = auto()
    QUANTCONNECT = auto()
    BACKTRADER = auto()
    FREQTRADE = auto()
    JESSE = auto()
    QSTRADER = auto()
    VECTORBT = auto()

    # ── News ──
    COINDESK_RSS = auto()
    NEWS_FEED = auto()
    ALPACA_NEWS = auto()
    NEWS_FANOUT = auto()

    # ── Social sentiment ──
    REDDIT_SENTIMENT = auto()
    X_SENTIMENT = auto()
    SOCIAL_SENTIMENT = auto()

    # ── On-chain analytics ──
    GLASSNODE = auto()
    NANSEN = auto()
    ARKHAM = auto()
    DUNE = auto()
    ETHERSCAN = auto()
    BITQUERY = auto()
    SOLANA_RPC = auto()
    ETHPLORER = auto()
    ONCHAIN_STREAMS = auto()

    # ── Macro / economic ──
    FRED_MACRO = auto()
    BLS_MACRO = auto()

    # ── Sensory / learning ──
    TECHNICAL_INDICATORS = auto()
    NEUROMORPHIC_PULSE = auto()
    DYON_ANOMALY = auto()
    GOVERNANCE_RISK = auto()
    SNN_LIF = auto()
    SNNTORCH = auto()
    NENGO_COGNITIVE = auto()
    SPYKE_ENCODER = auto()
    WEB_AUTOLEARN = auto()
    TRADER_INTELLIGENCE = auto()
    LEARNING_ENGINE = auto()

    # ── Sensory domains ──
    VOICE = auto()
    REGULATORY = auto()
    ALT_SENSORY = auto()
    COGNITIVE_SENSORY = auto()
    DEV_SENSORY = auto()

    # ── Infrastructure bridges ──
    KAFKA_EVENTS = auto()
    KAFKA_EVENT_BRIDGE = auto()
    DUCKDB_ANALYTICS = auto()
    QDRANT_MEMORY = auto()
    QDRANT_MEMORY_BRIDGE = auto()

    # ── mind/sources providers ──
    MIND_MARKET_CEX = auto()
    MIND_MARKET_EXPANDED = auto()
    MIND_MARKET_STREAMS = auto()
    MIND_NEWS = auto()
    MIND_NEWS_EXPANDED = auto()
    MIND_NEWS_STREAMS = auto()
    MIND_SENTIMENT = auto()
    MIND_SENTIMENT_STREAMS = auto()
    MIND_API_SNIFFER = auto()
    MIND_CODE_SEARCH = auto()

    # ── Integration platforms ──
    LIGHTNING_TRAINER = auto()
    RAY_COMPUTE = auto()
    TEMPORAL_WORKFLOWS = auto()
    LANGGRAPH_ORCHESTRATOR = auto()
    HAYSTACK_RAG = auto()
    FEAST_FEATURES = auto()
    OTEL_METRICS = auto()
    OTEL_TRACING = auto()
    OPA_POLICY = auto()
    OPA_GOVERNANCE_BRIDGE = auto()

    # ── Feed runners ──
    FEED_RUNNER = auto()
    RAYDIUM_RUNNER = auto()
    PUMPFUN_RUNNER = auto()
    FEEDS_ROUTES = auto()

    # ── Web autolearn variants ──
    CRAWLER_FIRECRAWL = auto()
    CRAWLER_PLAYWRIGHT = auto()
    CRAWLER_SCRAPY = auto()
    N8N_PIPELINE = auto()

    # ── Paper / simulation ──
    PAPER_TRADING = auto()


@dataclass(frozen=True, slots=True)
class IngestedTick:
    """Canonical market tick after ingestion normalization."""

    source: IngestionSource
    symbol: str
    price: float
    volume: float
    ts_ns: int
    raw_payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IngestionMetrics:
    """Telemetry for the ingestion bus."""

    ticks_received: int = 0
    ticks_dropped: int = 0
    last_tick_ts_ns: int = 0
    sources_connected: int = 0


class IngestionBus:
    """Unified ingestion pipeline.

    Receives ticks from multiple async sources, normalizes them, and:
    1. Updates RuntimeAuthority market state
    2. Forwards normalized ticks to the decision pipeline
    """

    def __init__(
        self,
        *,
        store: RuntimeAuthorityStore,
        writer_token: WriterToken,
        queue_size: int = 10000,
    ) -> None:
        self._store = store
        self._writer = writer_token
        self._queue: asyncio.Queue[IngestedTick] = asyncio.Queue(maxsize=queue_size)
        self._metrics = IngestionMetrics()
        self._running = False

    @property
    def metrics(self) -> IngestionMetrics:
        return self._metrics

    async def ingest(self, tick: IngestedTick) -> bool:
        """Submit a tick to the ingestion bus.

        Returns False if queue is full (backpressure).
        """
        try:
            self._queue.put_nowait(tick)
            self._metrics = IngestionMetrics(
                ticks_received=self._metrics.ticks_received + 1,
                ticks_dropped=self._metrics.ticks_dropped,
                last_tick_ts_ns=tick.ts_ns,
                sources_connected=self._metrics.sources_connected,
            )
            return True
        except asyncio.QueueFull:
            self._metrics = IngestionMetrics(
                ticks_received=self._metrics.ticks_received,
                ticks_dropped=self._metrics.ticks_dropped + 1,
                last_tick_ts_ns=self._metrics.last_tick_ts_ns,
                sources_connected=self._metrics.sources_connected,
            )
            return False

    async def consume(self) -> AsyncIterator[IngestedTick]:
        """Consume normalized ticks from the bus.

        Used by the decision pipeline to receive market data.
        """
        self._running = True
        while self._running:
            try:
                tick = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                # Update RuntimeAuthority with latest market state
                self._writer.write(
                    tick.ts_ns,
                    last_market_ts_ns=tick.ts_ns,
                    market_connected=True,
                )
                yield tick
            except TimeoutError:
                continue

    def stop(self) -> None:
        """Signal the consumer to stop."""
        self._running = False
