"""execution_engine.adapters.base — Base Adapter Protocol (INV-68 / Build Directive §6).

All execution adapters (CCXT, Hummingbot, Paper, UniswapX, Solana, PumpFun,
Raydium) extend this base. The adapter is the LAST link in the authority chain:
  Indira → ExecutionIntent → GovernanceEngine → ExecutionEngine → Adapter → Broker

Adapters MUST:
- Accept only governance-signed ExecutionIntents
- Validate HMAC signature before routing to broker
- Report all fills back through the reconciliation pipeline
- Emit PAPER_EXECUTED / LIVE_EXECUTED events to the ledger
- Respect domain isolation (NORMAL/COPY_TRADING/MEMECOIN never cross)
- Be replay-safe (accept TimeAuthority for timestamp injection)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from system import time_source


class AdapterStatus(StrEnum):
    """Adapter lifecycle status."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


class AdapterCapability(StrEnum):
    """Capabilities an adapter may declare."""

    SPOT = "SPOT"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    DEX_AMM = "DEX_AMM"
    DEX_CLOB = "DEX_CLOB"
    PAPER = "PAPER"


@dataclass(frozen=True, slots=True)
class AdapterConfig:
    """Configuration for a broker adapter."""

    adapter_id: str
    exchange: str
    domain: str
    capabilities: tuple[AdapterCapability, ...]
    max_retries: int = 3
    timeout_ms: int = 5000
    rate_limit_per_sec: float = 10.0


@dataclass(frozen=True, slots=True)
class FillReport:
    """Execution fill report from the broker."""

    adapter_id: str
    intent_id: str
    exchange_order_id: str
    symbol: str
    side: str
    filled_qty: float
    filled_price: float
    fee: float
    fee_currency: str
    latency_ms: float
    ts_ns: int = field(default_factory=time_source.wall_ns)
    partial: bool = False
    remaining_qty: float = 0.0


@dataclass(frozen=True, slots=True)
class AdapterHealth:
    """Health report for a connected adapter."""

    adapter_id: str
    status: AdapterStatus
    last_heartbeat_ns: int
    latency_p50_ms: float
    latency_p99_ms: float
    error_count_1m: int
    fill_count_session: int
    ts_ns: int = field(default_factory=time_source.wall_ns)


class BaseAdapter(ABC):
    """Abstract base for all execution adapters.

    Concrete implementations must override submit_order, cancel_order,
    get_balances, and the health check methods.
    """

    __slots__ = ("_config", "_status", "_fill_count", "_error_count", "_last_heartbeat_ns")

    def __init__(self, config: AdapterConfig) -> None:
        self._config = config
        self._status = AdapterStatus.DISCONNECTED
        self._fill_count = 0
        self._error_count = 0
        self._last_heartbeat_ns = 0

    @property
    def adapter_id(self) -> str:
        return self._config.adapter_id

    @property
    def exchange(self) -> str:
        return self._config.exchange

    @property
    def domain(self) -> str:
        return self._config.domain

    @property
    def status(self) -> AdapterStatus:
        return self._status

    @property
    def capabilities(self) -> tuple[AdapterCapability, ...]:
        return self._config.capabilities

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the exchange/broker.

        Returns:
            True if connected successfully.
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully disconnect from the exchange/broker."""
        ...

    @abstractmethod
    async def submit_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        *,
        intent_id: str = "",
        params: dict[str, Any] | None = None,
    ) -> FillReport:
        """Submit an order to the exchange.

        Args:
            symbol: Trading pair.
            side: BUY or SELL.
            order_type: MARKET, LIMIT, STOP, etc.
            quantity: Order size.
            price: Limit price (None for market orders).
            intent_id: Governance-signed intent ID for tracing.
            params: Exchange-specific parameters.

        Returns:
            FillReport with execution details.
        """
        ...

    @abstractmethod
    async def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        """Cancel a pending order.

        Returns:
            True if successfully cancelled.
        """
        ...

    @abstractmethod
    async def get_balances(self) -> dict[str, float]:
        """Get current account balances.

        Returns:
            Mapping of asset → available balance.
        """
        ...

    async def health_check(self) -> AdapterHealth:
        """Return current adapter health status."""
        return AdapterHealth(
            adapter_id=self.adapter_id,
            status=self._status,
            last_heartbeat_ns=self._last_heartbeat_ns,
            latency_p50_ms=0.0,
            latency_p99_ms=0.0,
            error_count_1m=self._error_count,
            fill_count_session=self._fill_count,
        )

    def _record_fill(self) -> None:
        """Increment fill counter."""
        self._fill_count += 1
        self._last_heartbeat_ns = time_source.wall_ns()

    def _record_error(self) -> None:
        """Increment error counter."""
        self._error_count += 1


# Backward-compatible alias (previously named BrokerAdapter)
BrokerAdapter = BaseAdapter

__all__ = [
    "AdapterCapability",
    "AdapterConfig",
    "AdapterHealth",
    "AdapterStatus",
    "BaseAdapter",
    "BrokerAdapter",
    "FillReport",
]
