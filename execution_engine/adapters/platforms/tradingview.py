"""TradingView platform integration (Paper-S3).

Read-only adapter for TradingView webhook signals, Pine Script
strategy results, and alert-based execution triggers.

__capability_tier__ = 0
__forbidden_tiers__ = (5,)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

__capability_tier__ = 0
__forbidden_tiers__ = (5,)


class TVAlertType(StrEnum):
    """TradingView alert types."""

    STRATEGY_ENTRY = "strategy_entry"
    STRATEGY_EXIT = "strategy_exit"
    INDICATOR_CROSS = "indicator_cross"
    PRICE_ALERT = "price_alert"
    VOLUME_SPIKE = "volume_spike"


@dataclass(frozen=True, slots=True)
class TVSignal:
    """Signal from TradingView webhook/alert."""

    alert_id: str
    alert_type: TVAlertType
    symbol: str
    side: str  # "long" | "short" | "close"
    price: float
    timeframe: str
    strategy_name: str
    confidence: float
    ts_ns: int


@dataclass(frozen=True, slots=True)
class TVStrategyResult:
    """Backtest result from a TradingView Pine Script strategy."""

    strategy_name: str
    symbol: str
    timeframe: str
    net_profit_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int
    profit_factor: float


class TradingViewAdapter:
    """Read-only adapter for TradingView platform.

    Receives webhook alerts and strategy results.
    Never sends orders — observation only.
    """

    def __init__(self, *, webhook_secret: str = "") -> None:
        self._secret = webhook_secret
        self._signals: list[TVSignal] = []
        self._strategies: dict[str, TVStrategyResult] = {}

    def fetch_signals(self, *, since_ts_ns: int = 0, limit: int = 50) -> list[TVSignal]:
        """Fetch recent TV signals."""
        return [s for s in self._signals if s.ts_ns >= since_ts_ns][:limit]

    def fetch_strategy_results(
        self, *, symbol: str = "", timeframe: str = ""
    ) -> list[TVStrategyResult]:
        """Fetch stored strategy backtest results."""
        results = list(self._strategies.values())
        if symbol:
            results = [r for r in results if r.symbol == symbol]
        if timeframe:
            results = [r for r in results if r.timeframe == timeframe]
        return results

    def ingest_webhook(self, payload: dict[str, Any], ts_ns: int = 0) -> TVSignal | None:
        """Process an incoming TradingView webhook payload."""
        try:
            signal = TVSignal(
                alert_id=payload.get("alert_id", ""),
                alert_type=TVAlertType(payload.get("type", "price_alert")),
                symbol=payload.get("symbol", ""),
                side=payload.get("side", ""),
                price=float(payload.get("price", 0)),
                timeframe=payload.get("timeframe", ""),
                strategy_name=payload.get("strategy", ""),
                confidence=float(payload.get("confidence", 0.5)),
                ts_ns=ts_ns,
            )
            self._signals.append(signal)
            return signal
        except (ValueError, KeyError):
            return None
