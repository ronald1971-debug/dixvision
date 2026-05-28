"""Jesse read-only adapter (BUILD-DIRECTIVE §11).

__capability_tier__ = 0
Exposes only fetch_* methods. No submit/execute/trade.
"""

from __future__ import annotations

__capability_tier__ = 0
__forbidden_tiers__ = (5,)

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class JesseSignal:
    """Normalized Jesse strategy signal."""

    strategy: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    stop_loss: float
    take_profit: float
    ts_ns: int


@dataclass(frozen=True, slots=True)
class JesseCandle:
    """Normalized Jesse candle (OHLCV)."""

    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    ts_ns: int


class JesseAdapter:
    """Read-only adapter for Jesse backtesting framework."""

    name: str = "jesse"

    def fetch_signals(
        self, *, raw_signals: list[dict[str, Any]]
    ) -> list[JesseSignal]:
        """Normalize Jesse strategy signal records."""
        return [
            JesseSignal(
                strategy=str(s.get("strategy", s.get("class_name", ""))),
                symbol=str(s.get("symbol", s.get("pair", ""))),
                side=str(s.get("side", s.get("position_type", ""))).upper(),
                qty=float(s.get("qty", s.get("quantity", 0.0))),
                entry_price=float(s.get("entry_price", s.get("price", 0.0))),
                stop_loss=float(s.get("stop_loss", s.get("sl", 0.0))),
                take_profit=float(s.get("take_profit", s.get("tp", 0.0))),
                ts_ns=int(s.get("ts_ns", s.get("timestamp", 0))),
            )
            for s in raw_signals
        ]

    def fetch_backtests(
        self, *, raw_backtests: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Normalize Jesse backtest result records."""
        return [
            {
                "platform": self.name,
                "strategy": str(b.get("strategy", b.get("class_name", ""))),
                "symbol": str(b.get("symbol", b.get("pair", ""))),
                "timeframe": str(b.get("timeframe", "4h")),
                "total_return": float(b.get("total_return", b.get("net_profit_pct", 0.0))),
                "sharpe": float(b.get("sharpe_ratio", b.get("sharpe", 0.0))),
                "max_drawdown": float(b.get("max_drawdown", 0.0)),
                "trades": int(b.get("total_completed_trades", b.get("trades", 0))),
                "win_rate": float(b.get("win_rate", 0.0)),
                "annual_return": float(b.get("annual_return", 0.0)),
            }
            for b in raw_backtests
        ]

    def fetch_market_data(
        self, *, raw_candles: list[dict[str, Any]], symbol: str = "", timeframe: str = "1d"
    ) -> list[JesseCandle]:
        """Normalize Jesse candle data (OHLCV)."""
        return [
            JesseCandle(
                symbol=str(c.get("symbol", symbol)),
                timeframe=str(c.get("timeframe", timeframe)),
                open=float(c.get("open", c.get("o", 0.0))),
                high=float(c.get("high", c.get("h", 0.0))),
                low=float(c.get("low", c.get("l", 0.0))),
                close=float(c.get("close", c.get("c", 0.0))),
                volume=float(c.get("volume", c.get("v", 0.0))),
                ts_ns=int(c.get("ts_ns", c.get("timestamp", 0))),
            )
            for c in raw_candles
        ]

    def fetch_strategy_results(
        self, *, raw_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Normalize Jesse strategy performance summary."""
        return {
            "platform": self.name,
            "strategy": str(raw_results.get("strategy", raw_results.get("class_name", ""))),
            "sharpe": float(raw_results.get("sharpe_ratio", raw_results.get("sharpe", 0.0))),
            "max_drawdown": float(raw_results.get("max_drawdown", 0.0)),
            "total_return": float(
                raw_results.get("total_return", raw_results.get("net_profit_pct", 0.0))
            ),
            "trades": int(
                raw_results.get("total_completed_trades", raw_results.get("trades", 0))
            ),
            "win_rate": float(raw_results.get("win_rate", 0.0)),
            "calmar_ratio": float(raw_results.get("calmar_ratio", 0.0)),
            "serenity_index": float(raw_results.get("serenity_index", 0.0)),
        }


__all__ = ["JesseAdapter", "JesseCandle", "JesseSignal"]
