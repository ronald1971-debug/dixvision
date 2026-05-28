"""VectorBT read-only adapter (BUILD-DIRECTIVE §13).

Fetches vectorized backtest analytics from VectorBT.
B-FETCH enforced: only fetch_* methods permitted.
"""

from __future__ import annotations

from typing import Any


class VectorBTAdapter:
    """Read-only adapter for VectorBT data ingestion."""

    platform: str = "vectorbt"

    def fetch_backtests(self, *, backtest_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fetch VectorBT backtest results."""
        return [
            {
                "platform": self.platform,
                "symbol": b.get("symbol", ""),
                "signal": b.get("signal", ""),
                "confidence": float(b.get("confidence", 0.0)),
                "total_return": float(b.get("total_return", 0.0)),
                "sharpe": float(b.get("sharpe", 0.0)),
                "max_drawdown": float(b.get("max_drawdown", 0.0)),
            }
            for b in backtest_data
        ]

    def fetch_strategy_results(
        self, *, strategy_data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Fetch VectorBT strategy analytics."""
        return [
            {
                "platform": self.platform,
                "strategy": s.get("strategy", ""),
                "metrics": s.get("metrics", {}),
            }
            for s in strategy_data
        ]
