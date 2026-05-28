"""QSTrader read-only adapter (BUILD-DIRECTIVE §11).

__capability_tier__ = 0
Exposes only fetch_* methods. No submit/execute/trade.
"""

from __future__ import annotations

__capability_tier__ = 0
__forbidden_tiers__ = (5,)

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class QSTraderSignal:
    """Normalized QSTrader portfolio signal."""

    strategy: str
    universe: str
    asset: str
    target_weight: float
    current_weight: float
    action: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class QSTraderBar:
    """Normalized price bar from QSTrader data handler."""

    asset: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    adj_close: float
    ts_ns: int


class QSTraderAdapter:
    """Read-only adapter for QSTrader institutional backtesting."""

    name: str = "qstrader"

    def fetch_signals(
        self, *, raw_signals: list[dict[str, Any]]
    ) -> list[QSTraderSignal]:
        """Normalize QSTrader portfolio rebalancing signal records."""
        return [
            QSTraderSignal(
                strategy=str(s.get("strategy", s.get("alpha_model", ""))),
                universe=str(s.get("universe", s.get("asset_universe", ""))),
                asset=str(s.get("asset", s.get("ticker", ""))),
                target_weight=float(s.get("target_weight", s.get("signal", 0.0))),
                current_weight=float(s.get("current_weight", 0.0)),
                action=str(s.get("action", "REBALANCE")).upper(),
                ts_ns=int(s.get("ts_ns", s.get("dt_ns", 0))),
            )
            for s in raw_signals
        ]

    def fetch_backtests(
        self, *, raw_backtests: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Normalize QSTrader portfolio backtest result records."""
        return [
            {
                "platform": self.name,
                "strategy": str(b.get("strategy", b.get("alpha_model", ""))),
                "universe": str(b.get("universe", "")),
                "total_return": float(b.get("total_return", b.get("cum_return", 0.0))),
                "sharpe": float(b.get("sharpe", b.get("annualised_sharpe", 0.0))),
                "max_drawdown": float(b.get("max_drawdown", 0.0)),
                "cagr": float(b.get("cagr", b.get("annualised_return", 0.0))),
                "trades": int(b.get("trades", b.get("total_rebalances", 0))),
                "volatility": float(b.get("volatility", b.get("annualised_vol", 0.0))),
                "sortino": float(b.get("sortino", 0.0)),
            }
            for b in raw_backtests
        ]

    def fetch_market_data(
        self,
        *,
        raw_prices: list[dict[str, Any]],
        symbol: str = "",
        timeframe: str = "1d",
    ) -> list[QSTraderBar]:
        """Normalize price bar records from a QSTrader data handler export."""
        return [
            QSTraderBar(
                asset=str(p.get("asset", p.get("ticker", symbol))),
                timeframe=str(p.get("timeframe", timeframe)),
                open=float(p.get("open", p.get("o", 0.0))),
                high=float(p.get("high", p.get("h", 0.0))),
                low=float(p.get("low", p.get("l", 0.0))),
                close=float(p.get("close", p.get("c", 0.0))),
                volume=float(p.get("volume", p.get("v", 0.0))),
                adj_close=float(p.get("adj_close", p.get("close", p.get("c", 0.0)))),
                ts_ns=int(p.get("ts_ns", p.get("dt_ns", 0))),
            )
            for p in raw_prices
        ]

    def fetch_strategy_results(
        self, *, raw_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Normalize QSTrader portfolio performance summary."""
        return {
            "platform": self.name,
            "strategy": str(raw_results.get("strategy", raw_results.get("alpha_model", ""))),
            "sharpe": float(
                raw_results.get("sharpe", raw_results.get("annualised_sharpe", 0.0))
            ),
            "max_drawdown": float(raw_results.get("max_drawdown", 0.0)),
            "total_return": float(
                raw_results.get("total_return", raw_results.get("cum_return", 0.0))
            ),
            "cagr": float(
                raw_results.get("cagr", raw_results.get("annualised_return", 0.0))
            ),
            "trades": int(
                raw_results.get("trades", raw_results.get("total_rebalances", 0))
            ),
            "sortino": float(raw_results.get("sortino", 0.0)),
            "information_ratio": float(raw_results.get("information_ratio", 0.0)),
        }


__all__ = ["QSTraderAdapter", "QSTraderBar", "QSTraderSignal"]
