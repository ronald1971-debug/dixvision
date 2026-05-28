"""Jesse read-only adapter (BUILD-DIRECTIVE §11).

__capability_tier__ = 0
Exposes only fetch_* methods. No submit/execute/trade.
"""

from __future__ import annotations

__capability_tier__ = 0
__forbidden_tiers__ = (5,)

from typing import Any


class JesseAdapter:
    """Read-only adapter for Jesse backtesting framework."""

    name: str = "jesse"

    def fetch_signals(self, *, strategy_name: str = "") -> list[dict[str, Any]]:
        """Fetch signals from a Jesse strategy."""
        return []

    def fetch_backtests(self, *, strategy_name: str = "", symbol: str = "") -> list[dict[str, Any]]:
        """Fetch Jesse backtest results."""
        return []

    def fetch_market_data(self, *, symbol: str, timeframe: str = "1d") -> list[dict[str, Any]]:
        """Fetch candle data from Jesse."""
        return []

    def fetch_strategy_results(self, *, strategy_name: str) -> dict[str, Any]:
        """Fetch Jesse strategy metrics."""
        return {
            "strategy": strategy_name,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "total_return": 0.0,
            "trades": 0,
            "win_rate": 0.0,
            "source_platform": "jesse",
        }
