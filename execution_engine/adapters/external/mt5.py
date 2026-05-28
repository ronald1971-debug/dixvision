"""MetaTrader 5 read-only adapter (BUILD-DIRECTIVE §13).

Fetches signal exports and market data from MT5.
B-FETCH enforced: only fetch_* methods permitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MT5Signal:
    """Normalized MT5 signal export."""

    symbol: str
    order_type: str
    volume: float
    price: float
    sl: float
    tp: float
    ts_ns: int


class MT5Adapter:
    """Read-only adapter for MetaTrader 5 data ingestion."""

    platform: str = "mt5"

    def fetch_signals(self, *, raw_signals: list[dict[str, Any]]) -> list[MT5Signal]:
        """Fetch and normalize MT5 signal exports."""
        return [
            MT5Signal(
                symbol=str(s.get("symbol", "")),
                order_type=str(s.get("type", "")),
                volume=float(s.get("volume", 0.0)),
                price=float(s.get("price", 0.0)),
                sl=float(s.get("sl", 0.0)),
                tp=float(s.get("tp", 0.0)),
                ts_ns=int(s.get("ts_ns", 0)),
            )
            for s in raw_signals
        ]

    def fetch_market_data(self, *, symbol: str, timeframe: str, bars: int) -> list[dict[str, Any]]:
        """Fetch OHLCV market data from MT5."""
        # Placeholder — actual implementation would connect to MT5 terminal
        return [
            {
                "platform": self.platform,
                "symbol": symbol,
                "timeframe": timeframe,
                "bars_requested": bars,
            }
        ]
