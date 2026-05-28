"""TradingView read-only adapter (BUILD-DIRECTIVE §13).

Fetches alerts, ideas, and strategy results from TradingView.
B-FETCH enforced: only fetch_* methods permitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TradingViewAlert:
    """Normalized TradingView alert."""

    symbol: str
    action: str
    price: float
    timeframe: str
    indicator: str
    ts_ns: int


class TradingViewAdapter:
    """Read-only adapter for TradingView data ingestion."""

    platform: str = "tradingview"

    def fetch_signals(self, *, raw_alerts: list[dict[str, Any]]) -> list[TradingViewAlert]:
        """Fetch and normalize TradingView alert signals."""
        results = []
        for alert in raw_alerts:
            results.append(
                TradingViewAlert(
                    symbol=str(alert.get("symbol", "")),
                    action=str(alert.get("action", "")),
                    price=float(alert.get("price", 0.0)),
                    timeframe=str(alert.get("timeframe", "1h")),
                    indicator=str(alert.get("indicator", "")),
                    ts_ns=int(alert.get("ts_ns", 0)),
                )
            )
        return results

    def fetch_strategy_results(
        self, *, strategy_data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Fetch TradingView strategy backtest results."""
        return [
            {
                "platform": self.platform,
                "strategy_name": s.get("name", ""),
                "symbol": s.get("symbol", ""),
                "net_profit_pct": float(s.get("net_profit_pct", 0.0)),
                "win_rate": float(s.get("win_rate", 0.0)),
                "max_drawdown_pct": float(s.get("max_drawdown_pct", 0.0)),
                "sharpe": float(s.get("sharpe", 0.0)),
                "total_trades": int(s.get("total_trades", 0)),
            }
            for s in strategy_data
        ]
