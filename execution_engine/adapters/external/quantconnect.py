"""QuantConnect read-only adapter (BUILD-DIRECTIVE §13).

Fetches backtest results and strategy analytics from QuantConnect.
B-FETCH enforced: only fetch_* methods permitted.
"""

from __future__ import annotations

from typing import Any


class QuantConnectAdapter:
    """Read-only adapter for QuantConnect data ingestion."""

    platform: str = "quantconnect"

    def fetch_backtests(self, *, backtest_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fetch QuantConnect backtest results."""
        return [
            {
                "platform": self.platform,
                "project_id": b.get("project_id", ""),
                "backtest_id": b.get("backtest_id", ""),
                "symbol": b.get("symbol", ""),
                "net_profit": float(b.get("net_profit", 0.0)),
                "sharpe": float(b.get("sharpe", 0.0)),
                "drawdown": float(b.get("drawdown", 0.0)),
                "total_trades": int(b.get("total_trades", 0)),
            }
            for b in backtest_data
        ]

    def fetch_strategy_results(
        self, *, strategy_data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Fetch QuantConnect live strategy performance data."""
        return [
            {
                "platform": self.platform,
                "strategy_name": s.get("name", ""),
                "direction": s.get("direction", ""),
                "quantity": int(s.get("quantity", 0)),
                "unrealized_pnl": float(s.get("unrealized_pnl", 0.0)),
            }
            for s in strategy_data
        ]
