"""Freqtrade read-only adapter (BUILD-DIRECTIVE §13).

Fetches strategy signals and backtest analytics from Freqtrade.
B-FETCH enforced: only fetch_* methods permitted.
"""

from __future__ import annotations

from typing import Any


class FreqtradeAdapter:
    """Read-only adapter for Freqtrade data ingestion."""

    platform: str = "freqtrade"

    def fetch_signals(self, *, raw_signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fetch Freqtrade strategy signals."""
        return [
            {
                "platform": self.platform,
                "pair": s.get("pair", ""),
                "side": s.get("side", ""),
                "stake_amount": float(s.get("stake_amount", 0.0)),
                "strategy": s.get("strategy", ""),
                "enter_tag": s.get("enter_tag", ""),
            }
            for s in raw_signals
        ]

    def fetch_backtests(self, *, backtest_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fetch Freqtrade backtest results."""
        return [
            {
                "platform": self.platform,
                "strategy": b.get("strategy", ""),
                "pair": b.get("pair", ""),
                "profit_total": float(b.get("profit_total", 0.0)),
                "win_rate": float(b.get("win_rate", 0.0)),
                "max_drawdown": float(b.get("max_drawdown", 0.0)),
                "trades": int(b.get("trades", 0)),
            }
            for b in backtest_data
        ]

    def fetch_strategy_results(
        self, *, strategy_data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Fetch Freqtrade live/dry-run strategy state."""
        return [
            {
                "platform": self.platform,
                "strategy": s.get("strategy", ""),
                "profit_pct": float(s.get("profit_pct", 0.0)),
                "open_trades": int(s.get("open_trades", 0)),
            }
            for s in strategy_data
        ]
