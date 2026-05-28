"""QSTrader read-only adapter (BUILD-DIRECTIVE §11).

__capability_tier__ = 0
Exposes only fetch_* methods. No submit/execute/trade.
"""

from __future__ import annotations

__capability_tier__ = 0
__forbidden_tiers__ = (5,)

from typing import Any


class QSTraderAdapter:
    """Read-only adapter for QSTrader institutional backtesting."""

    name: str = "qstrader"

    def fetch_signals(self, *, strategy_name: str = "") -> list[dict[str, Any]]:
        """Fetch signals from a QSTrader strategy."""
        return []

    def fetch_backtests(
        self, *, strategy_name: str = "", universe: str = ""
    ) -> list[dict[str, Any]]:
        """Fetch QSTrader backtest results."""
        return []

    def fetch_market_data(self, *, symbol: str, timeframe: str = "1d") -> list[dict[str, Any]]:
        """Fetch market data via QSTrader data handlers."""
        return []

    def fetch_strategy_results(self, *, strategy_name: str) -> dict[str, Any]:
        """Fetch QSTrader portfolio performance."""
        return {
            "strategy": strategy_name,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "total_return": 0.0,
            "cagr": 0.0,
            "trades": 0,
            "source_platform": "qstrader",
        }
