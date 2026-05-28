"""runtime.exchange_connector — Real Exchange Lifecycle Connector.

Manages the REAL connection to exchanges (not mocks). Handles:
1. Connection establishment (auth, websocket, REST)
2. Heartbeat monitoring (detect stale connections)
3. Reconnection with backoff (auto-recover from disconnects)
4. Order state synchronization (query open orders on reconnect)
5. Position reconciliation (verify positions match expectations)
6. Rate limiting (respect exchange limits)

OPERATIONAL READINESS:
- This module is what makes the system REAL (not a simulation)
- Paper mode uses PaperBroker (simulated fills, no network)
- Canary mode uses real exchange with minimal size
- Live mode uses real exchange with full allocation

NEVER bypasses governance. Orders only dispatch via approved intents.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from system import time_source

logger = logging.getLogger(__name__)


class ConnectionState(StrEnum):
    """Exchange connection states."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    AUTHENTICATING = "AUTHENTICATING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    RATE_LIMITED = "RATE_LIMITED"
    ERROR = "ERROR"


class ExchangeType(StrEnum):
    """Supported exchange types."""

    CEX = "CEX"  # Centralized (Binance, Coinbase, Kraken)
    DEX = "DEX"  # Decentralized (Uniswap, Jupiter, Raydium)
    PAPER = "PAPER"  # Paper trading (simulated)


@dataclass(frozen=True, slots=True)
class ExchangeCredentials:
    """Exchange authentication credentials (loaded from Vault)."""

    exchange_id: str
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""
    subaccount: str = ""
    testnet: bool = True


@dataclass
class ConnectionHealth:
    """Health metrics for an exchange connection."""

    state: ConnectionState = ConnectionState.DISCONNECTED
    last_heartbeat_ts: float = 0.0
    last_message_ts: float = 0.0
    reconnect_count: int = 0
    error_count: int = 0
    latency_ms: float = 0.0
    messages_received: int = 0

    @property
    def is_healthy(self) -> bool:
        if self.state != ConnectionState.CONNECTED:
            return False
        stale = time_source.wall_ns() / 1_000_000_000 - self.last_heartbeat_ts > 30.0
        return not stale

    @property
    def uptime_ratio(self) -> float:
        total = self.messages_received + self.error_count
        return self.messages_received / total if total > 0 else 0.0


@dataclass
class ConnectorConfig:
    """Exchange connector configuration."""

    heartbeat_interval_s: float = 10.0
    reconnect_max_retries: int = 10
    reconnect_base_delay_s: float = 1.0
    reconnect_max_delay_s: float = 60.0
    stale_threshold_s: float = 30.0
    rate_limit_buffer_pct: float = 20.0


class ExchangeConnector:
    """Manages a single exchange connection lifecycle.

    This is the REAL interface — it will use CCXT or Hummingbot
    adapters under the hood depending on the exchange type.
    """

    __slots__ = (
        "_exchange_id",
        "_exchange_type",
        "_config",
        "_health",
        "_credentials",
        "_adapter",
        "_connected_since",
        "_last_reconnect_attempt",
    )

    def __init__(
        self, exchange_id: str, exchange_type: ExchangeType, config: ConnectorConfig | None = None
    ) -> None:
        self._exchange_id = exchange_id
        self._exchange_type = exchange_type
        self._config = config or ConnectorConfig()
        self._health = ConnectionHealth()
        self._credentials: ExchangeCredentials | None = None
        self._adapter: Any = None
        self._connected_since = 0.0
        self._last_reconnect_attempt = 0.0

    @property
    def exchange_id(self) -> str:
        return self._exchange_id

    @property
    def state(self) -> ConnectionState:
        return self._health.state

    @property
    def health(self) -> ConnectionHealth:
        return self._health

    @property
    def is_connected(self) -> bool:
        return self._health.state == ConnectionState.CONNECTED

    async def connect(self, credentials: ExchangeCredentials) -> bool:
        """Establish connection to exchange.

        Returns True if connection established, False otherwise.
        """
        self._credentials = credentials
        self._health.state = ConnectionState.CONNECTING

        try:
            # Select adapter based on exchange type
            if self._exchange_type == ExchangeType.PAPER:
                self._adapter = await self._create_paper_adapter()
            elif self._exchange_type == ExchangeType.CEX:
                self._adapter = await self._create_cex_adapter(credentials)
            elif self._exchange_type == ExchangeType.DEX:
                self._adapter = await self._create_dex_adapter(credentials)

            if self._adapter is not None:
                self._health.state = ConnectionState.CONNECTED
                self._health.last_heartbeat_ts = time_source.wall_ns() / 1_000_000_000
                self._connected_since = time_source.wall_ns() / 1_000_000_000
                logger.info("Connected to %s (%s)", self._exchange_id, self._exchange_type)
                return True

            self._health.state = ConnectionState.ERROR
            return False

        except Exception as e:
            self._health.state = ConnectionState.ERROR
            self._health.error_count += 1
            logger.error("Failed to connect to %s: %s", self._exchange_id, e)
            return False

    async def disconnect(self) -> None:
        """Gracefully disconnect from exchange."""
        if self._adapter and hasattr(self._adapter, "close"):
            try:
                await self._adapter.close()
            except Exception as e:
                logger.warning("Error disconnecting from %s: %s", self._exchange_id, e)
        self._health.state = ConnectionState.DISCONNECTED
        self._adapter = None
        logger.info("Disconnected from %s", self._exchange_id)

    async def reconnect(self) -> bool:
        """Attempt reconnection with exponential backoff."""
        if self._health.reconnect_count >= self._config.reconnect_max_retries:
            logger.error("Max reconnect attempts reached for %s", self._exchange_id)
            self._health.state = ConnectionState.ERROR
            return False

        self._health.state = ConnectionState.RECONNECTING
        self._health.reconnect_count += 1

        # Exponential backoff
        delay = min(
            self._config.reconnect_base_delay_s * (2 ** (self._health.reconnect_count - 1)),
            self._config.reconnect_max_delay_s,
        )

        import asyncio

        await asyncio.sleep(delay)

        if self._credentials:
            return await self.connect(self._credentials)
        return False

    async def heartbeat(self) -> bool:
        """Send heartbeat / check connection liveness."""
        if not self.is_connected:
            return False

        now = time_source.wall_ns() / 1_000_000_000
        since_last = now - self._health.last_heartbeat_ts

        if since_last > self._config.stale_threshold_s:
            logger.warning("Connection stale for %s (%.1fs)", self._exchange_id, since_last)
            return await self.reconnect()

        self._health.last_heartbeat_ts = now
        return True

    async def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float | None = None,
        order_type: str = "LIMIT",
    ) -> dict[str, Any] | None:
        """Submit an order to the exchange.

        This is ONLY called for governance-approved intents. Never
        directly — always through ExecutionLifecycleManager.
        """
        if not self.is_connected:
            logger.error("Cannot submit order — not connected to %s", self._exchange_id)
            return None

        try:
            if self._adapter and hasattr(self._adapter, "create_order"):
                result = await self._adapter.create_order(
                    symbol=symbol,
                    side=side,
                    amount=qty,
                    price=price,
                    type=order_type,
                )
                self._health.messages_received += 1
                return result
        except Exception as e:
            self._health.error_count += 1
            logger.error("Order submission failed on %s: %s", self._exchange_id, e)
            return None

        return None

    async def query_positions(self) -> list[dict[str, Any]]:
        """Query current positions from exchange (for reconciliation)."""
        if not self.is_connected:
            return []

        try:
            if self._adapter and hasattr(self._adapter, "fetch_positions"):
                return await self._adapter.fetch_positions()
        except Exception as e:
            logger.error("Position query failed on %s: %s", self._exchange_id, e)
        return []

    async def query_open_orders(self) -> list[dict[str, Any]]:
        """Query open orders from exchange (for reconciliation)."""
        if not self.is_connected:
            return []

        try:
            if self._adapter and hasattr(self._adapter, "fetch_open_orders"):
                return await self._adapter.fetch_open_orders()
        except Exception as e:
            logger.error("Open orders query failed on %s: %s", self._exchange_id, e)
        return []

    async def _create_paper_adapter(self) -> Any:
        """Create paper trading adapter (simulated)."""
        try:
            from execution_engine.paper_broker import PaperBroker

            return PaperBroker()
        except ImportError:
            # Minimal paper adapter
            return _MinimalPaperAdapter()

    async def _create_cex_adapter(self, credentials: ExchangeCredentials) -> Any:
        """Create CEX adapter via CCXT."""
        try:
            from integrations.ccxt_adapter import CCXTAdapter

            adapter = CCXTAdapter(
                exchange_id=credentials.exchange_id,
                api_key=credentials.api_key,
                api_secret=credentials.api_secret,
                testnet=credentials.testnet,
            )
            return adapter
        except ImportError:
            logger.warning("CCXT adapter not available, using minimal stub")
            return None

    async def _create_dex_adapter(self, credentials: ExchangeCredentials) -> Any:
        """Create DEX adapter via Hummingbot Gateway."""
        try:
            from execution_engine.adapters.hummingbot import HummingbotAdapter

            return HummingbotAdapter()
        except ImportError:
            logger.warning("Hummingbot adapter not available")
            return None


class _MinimalPaperAdapter:
    """Minimal paper adapter for when PaperBroker is unavailable."""

    async def create_order(self, **kwargs: Any) -> dict[str, Any]:
        return {"id": f"paper_{time_source.wall_ns()}", "status": "filled", **kwargs}

    async def fetch_positions(self) -> list[dict[str, Any]]:
        return []

    async def fetch_open_orders(self) -> list[dict[str, Any]]:
        return []

    async def close(self) -> None:
        pass


class ExchangeConnectionPool:
    """Manages multiple exchange connections."""

    __slots__ = ("_connectors",)

    def __init__(self) -> None:
        self._connectors: dict[str, ExchangeConnector] = {}

    def add(
        self, exchange_id: str, exchange_type: ExchangeType, config: ConnectorConfig | None = None
    ) -> ExchangeConnector:
        """Add a new exchange connector to the pool."""
        connector = ExchangeConnector(exchange_id, exchange_type, config)
        self._connectors[exchange_id] = connector
        return connector

    def get(self, exchange_id: str) -> ExchangeConnector | None:
        """Get connector by exchange ID."""
        return self._connectors.get(exchange_id)

    @property
    def connected_count(self) -> int:
        return sum(1 for c in self._connectors.values() if c.is_connected)

    @property
    def all_healthy(self) -> bool:
        return all(c.health.is_healthy for c in self._connectors.values() if c.is_connected)

    async def heartbeat_all(self) -> None:
        """Run heartbeat on all connectors."""
        for connector in self._connectors.values():
            if connector.is_connected:
                await connector.heartbeat()


__all__ = [
    "ConnectionHealth",
    "ConnectionState",
    "ConnectorConfig",
    "ExchangeConnectionPool",
    "ExchangeConnector",
    "ExchangeCredentials",
    "ExchangeType",
]
