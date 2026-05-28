"""core.contracts.execution — Execution Protocol & Value Types (INV-68).

ExecutionIntent is the ONLY token that execution accepts. It flows through:
  Indira → ExecutionIntent → GovernanceEngine → ExecutionEngine → Adapter → Broker

No other path. Indira never calls a broker. The ExecutionGate (INV-68) is the
mandatory chokepoint for all external trade dispatch.

Capability tiers for execution:
  Tier 2: Simulation (paper/backtest)
  Tier 4: Governed paper execution
  Tier 5: Live execution (only via OperatorAuthority.LiveExecution=ARMED)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from system import time_source

__capability_tier__ = 4
__forbidden_tiers__ = (5,)


class OrderSide(StrEnum):
    """Trade direction."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    """Supported order types through the execution gate."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"


class ExecutionMode(StrEnum):
    """Execution routing mode — determines which broker adapters are used."""

    PAPER = "PAPER"
    BACKTEST = "BACKTEST"
    LIVE = "LIVE"


class FillStatus(StrEnum):
    """Order fill lifecycle status."""

    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ActionClass(StrEnum):
    """Semi-auto action classification for threshold gating."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"
    RISK_REDUCE = "RISK_REDUCE"
    REBALANCE = "REBALANCE"


@dataclass(frozen=True, slots=True)
class ExecutionIntent:
    """The ONLY token execution accepts (INV-68).

    Constructed by intelligence_engine (FULL_AUTO/SEMI_AUTO modes) or by the
    dashboard order ticket (MANUAL mode). No other producer allowed.
    Immutable once constructed. Governance signs and routes to adapter.
    """

    intent_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float | None
    mode: ExecutionMode
    domain: str
    action_class: ActionClass
    source: str
    confidence: float
    trace_id: str
    ts_ns: int = field(default_factory=time_source.wall_ns)
    stop_price: float | None = None
    take_profit_price: float | None = None
    time_in_force: str = "GTC"
    max_slippage_bps: float = 50.0
    governance_signature: str = ""

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            msg = "quantity must be > 0"
            raise ValueError(msg)
        if not self.intent_id:
            msg = "intent_id must be non-empty"
            raise ValueError(msg)
        if not self.symbol:
            msg = "symbol must be non-empty"
            raise ValueError(msg)
        if not (0.0 <= self.confidence <= 1.0):
            msg = "confidence must be in [0, 1]"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Result of processing an ExecutionIntent through the gate."""

    intent_id: str
    status: FillStatus
    filled_quantity: float
    filled_price: float
    fee_usd: float
    slippage_bps: float
    latency_ms: float
    adapter_id: str
    ts_ns: int = field(default_factory=time_source.wall_ns)
    error: str = ""
    partial_fills: int = 0


@dataclass(frozen=True, slots=True)
class PositionUpdate:
    """Position state change after execution."""

    symbol: str
    side: OrderSide
    quantity: float
    avg_entry_price: float
    unrealized_pnl: float
    realized_pnl: float
    exposure_usd: float
    ts_ns: int = field(default_factory=time_source.wall_ns)


@runtime_checkable
class IExecution(Protocol):
    """Protocol: execution engine contract.

    Only the ExecutionGate (INV-68) routes intents to the broker via this
    protocol. All governance checks must pass before reaching this layer.
    """

    def process_intent(self, intent: ExecutionIntent) -> ExecutionResult:
        """Route a governance-approved intent to the appropriate adapter.

        Args:
            intent: Governance-signed ExecutionIntent (signature verified).

        Returns:
            ExecutionResult with fill details and timing.

        Raises:
            ValueError: If governance_signature is missing or invalid.
        """
        ...

    def cancel(self, intent_id: str) -> bool:
        """Cancel a pending order by intent ID.

        Returns:
            True if cancelled, False if already filled or not found.
        """
        ...

    def get_position(self, symbol: str) -> PositionUpdate | None:
        """Get current position for a symbol."""
        ...

    def get_open_orders(self) -> list[ExecutionIntent]:
        """Return all orders currently pending execution."""
        ...

    def start(self) -> None:
        """Start the execution engine and connect adapters."""
        ...

    def stop(self) -> None:
        """Gracefully stop the execution engine and disconnect adapters."""
        ...

    @property
    def is_running(self) -> bool:
        """Whether the execution engine is actively processing."""
        ...


__all__ = [
    "ActionClass",
    "ExecutionIntent",
    "ExecutionMode",
    "ExecutionResult",
    "FillStatus",
    "IExecution",
    "OrderSide",
    "OrderType",
    "PositionUpdate",
]
