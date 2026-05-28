"""Backtrader read-only adapter (BUILD-DIRECTIVE §11).

__capability_tier__ = 0
Exposes only fetch_* methods. No submit/execute/trade.
"""

from __future__ import annotations

__capability_tier__ = 0
__forbidden_tiers__ = (5,)

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BacktraderSignal:
    """Normalized Backtrader strategy signal."""

    strategy: str
    symbol: str
    side: str
    size: float
    price: float
    ts_ns: int


@dataclass(frozen=True, slots=True)
class BacktraderBar:
    """Normalized OHLCV bar from a Backtrader data feed."""

    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    ts_ns: int


class BacktraderAdapter:
    """Read-only adapter for Backtrader backtesting results."""

    name: str = "backtrader"

    def fetch_signals(
        self, *, raw_signals: list[dict[str, Any]]
    ) -> list[BacktraderSignal]:
        """Normalize Backtrader strategy signal records."""
        return [
            BacktraderSignal(
                strategy=str(s.get("strategy", "")),
                symbol=str(s.get("symbol", s.get("data", ""))),
                side=str(s.get("side", s.get("order_type", ""))).upper(),
                size=float(s.get("size", s.get("quantity", 0.0))),
                price=float(s.get("price", 0.0)),
                ts_ns=int(s.get("ts_ns", s.get("timestamp_ns", 0))),
            )
            for s in raw_signals
        ]

    def fetch_backtests(
        self, *, raw_backtests: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Normalize Backtrader backtest result records."""
        return [
            {
                "platform": self.name,
                "strategy": str(b.get("strategy", "")),
                "symbol": str(b.get("symbol", b.get("data", ""))),
                "total_return": float(b.get("pnl", b.get("total_return", 0.0))),
                "sharpe": float(b.get("sharpe", 0.0)),
                "max_drawdown": float(b.get("max_drawdown", b.get("drawdown", 0.0))),
                "trades": int(b.get("trades", b.get("total_trades", 0))),
                "win_rate": float(b.get("win_rate", 0.0)),
            }
            for b in raw_backtests
        ]

    def fetch_market_data(
        self, *, raw_bars: list[dict[str, Any]], symbol: str = "", timeframe: str = "1d"
    ) -> list[BacktraderBar]:
        """Normalize OHLCV bars from a Backtrader data feed export."""
        return [
            BacktraderBar(
                symbol=str(b.get("symbol", symbol)),
                timeframe=str(b.get("timeframe", timeframe)),
                open=float(b.get("open", b.get("o", 0.0))),
                high=float(b.get("high", b.get("h", 0.0))),
                low=float(b.get("low", b.get("l", 0.0))),
                close=float(b.get("close", b.get("c", 0.0))),
                volume=float(b.get("volume", b.get("v", 0.0))),
                ts_ns=int(b.get("ts_ns", b.get("timestamp_ns", 0))),
            )
            for b in raw_bars
        ]

    def fetch_strategy_results(
        self, *, raw_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Normalize Backtrader strategy performance summary."""
        return {
            "platform": self.name,
            "strategy": str(raw_results.get("strategy", "")),
            "sharpe": float(raw_results.get("sharpe", 0.0)),
            "max_drawdown": float(
                raw_results.get("max_drawdown", raw_results.get("drawdown", 0.0))
            ),
            "total_return": float(
                raw_results.get("total_return", raw_results.get("pnl", 0.0))
            ),
            "trades": int(raw_results.get("trades", raw_results.get("total_trades", 0))),
            "win_rate": float(raw_results.get("win_rate", 0.0)),
            "profit_factor": float(raw_results.get("profit_factor", 0.0)),
        }


__all__ = ["BacktraderAdapter", "BacktraderBar", "BacktraderSignal"]
