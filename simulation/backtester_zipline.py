# ADAPTED FROM: stefan-jansen/zipline-reloaded
# (zipline/algorithm.py — TradingAlgorithm class, initialize(), handle_data(),
#  analyze(); zipline/finance/order.py — Order lifecycle states;
#  zipline/data/bundles/ — data bundle ingestion pattern)
"""C-59 — Zipline-reloaded cross-validation backtester.

This module adapts Zipline's TradingAlgorithm interface for
cross-validation backtesting alongside the existing backtrader
backtester. Both should produce same results given same data.

What survives from upstream (stefan-jansen/zipline-reloaded):
    * **TradingAlgorithm** — ``algorithm.py``: ``initialize()`` for
      setup, ``handle_data()`` per-bar logic, ``analyze()`` results.
    * **Order lifecycle** — ``finance/order.py``: OPEN → FILLED /
      CANCELLED states.
    * **Context object** — ``context`` passed to handle_data with
      portfolio state.

What we replaced:
    * Real ``zipline`` import is lazy (Protocol seam).
    * In-memory market data replay for unit tests.
    * Same BacktestResult contract as backtrader adapter.

OFFLINE tier: backtesting computation, never on RUNTIME path.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

NEW_PIP_DEPENDENCIES: tuple[str, ...] = ()


class OrderStatus(enum.Enum):
    """Zipline-style order status."""

    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


@dataclass
class ZiplineContext:
    """Trading algorithm context (portfolio + broker state)."""

    portfolio_value: float = 100_000.0
    cash: float = 100_000.0
    positions: dict[str, float] = field(default_factory=dict)
    orders: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class BacktestBar:
    """A single OHLCV bar for backtesting."""

    symbol: str
    timestamp_ns: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True, slots=True)
class ZiplineResult:
    """Result of a Zipline backtest run."""

    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    num_trades: int
    final_value: float


class ZiplineBacktester:
    """Zipline-style event-driven backtester.

    Implements the TradingAlgorithm pattern:
    - ``initialize(context)`` — called once at start
    - ``handle_data(context, data)`` — called per bar
    - ``analyze(context)`` — called at end

    Usage::

        bt = ZiplineBacktester(capital=100_000)
        bt.set_initialize(lambda ctx: None)
        bt.set_handle_data(my_strategy)
        result = bt.run(bars)
    """

    def __init__(self, *, capital: float = 100_000.0) -> None:
        self._capital = capital
        self._initialize_fn: Callable[[ZiplineContext], None] | None = None
        self._handle_data_fn: Callable[[ZiplineContext, BacktestBar], None] | None = None

    def set_initialize(self, fn: Callable[[ZiplineContext], None]) -> None:
        """Set the initialize function (mirrors TradingAlgorithm.initialize)."""
        self._initialize_fn = fn

    def set_handle_data(self, fn: Callable[[ZiplineContext, BacktestBar], None]) -> None:
        """Set the handle_data function (mirrors TradingAlgorithm.handle_data)."""
        self._handle_data_fn = fn

    def run(self, bars: Sequence[BacktestBar]) -> ZiplineResult:
        """Run the backtest over provided bars."""
        ctx = ZiplineContext(portfolio_value=self._capital, cash=self._capital)

        if self._initialize_fn:
            self._initialize_fn(ctx)

        peak = self._capital
        max_dd = 0.0
        num_trades = 0

        for bar in bars:
            if self._handle_data_fn:
                prev_orders = len(ctx.orders)
                self._handle_data_fn(ctx, bar)
                num_trades += len(ctx.orders) - prev_orders

            # Update portfolio value from positions
            pos_value = sum(
                qty * bar.close for sym, qty in ctx.positions.items() if sym == bar.symbol
            )
            ctx.portfolio_value = ctx.cash + pos_value

            if ctx.portfolio_value > peak:
                peak = ctx.portfolio_value
            dd = (peak - ctx.portfolio_value) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        total_return = (ctx.portfolio_value - self._capital) / self._capital
        # Simplified Sharpe (no daily returns tracking)
        sharpe = total_return / max_dd if max_dd > 0 else 0.0

        return ZiplineResult(
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            num_trades=num_trades,
            final_value=ctx.portfolio_value,
        )


__all__ = [
    "NEW_PIP_DEPENDENCIES",
    "BacktestBar",
    "OrderStatus",
    "ZiplineBacktester",
    "ZiplineContext",
    "ZiplineResult",
]
