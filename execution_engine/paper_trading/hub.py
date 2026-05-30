"""execution_engine.paper_trading.hub — Unified paper trading hub.

PaperTradingHub owns six PaperVenueAdapter instances (one per exchange) and
provides:
  * Signal routing — submit() dispatches to the right adapter by name or
    by domain-based heuristic (forex → OANDA, equity → IBKR/Alpaca, etc.)
  * Aggregate portfolio view — snapshot() collates all six portfolios
  * P&L summary — realized_pnl() and pnl_summary() across all venues
  * Per-venue reset — reset_venue() and reset_all()

Domain routing heuristic (overridable via signal.meta["paper_venue"]):
  symbol contains "_" (e.g. "EUR_USD") → oanda_paper
  symbol prefix in EQUITY_PREFIXES      → ibkr_paper (or alpaca_paper)
  default                               → binance_paper

The operator can override routing by setting signal.meta["paper_venue"]
to any registered adapter name.

Authority: execution_engine.paper_trading.* + core.* only.
INV-56: paper fills are tagged paper=1 throughout.
"""

from __future__ import annotations

import threading
from typing import Any

from core.contracts.events import ExecutionEvent, SignalEvent
from execution_engine.paper_trading.adapter import PaperVenueAdapter
from execution_engine.paper_trading.venue_config import (
    ALPACA_PAPER,
    BINANCE_PAPER,
    COINBASE_PAPER,
    IBKR_PAPER,
    KRAKEN_PAPER,
    OANDA_PAPER,
    VENUE_CONFIGS,
    VenueConfig,
)

# Equity ticker prefixes that suggest Alpaca/IBKR routing
_EQUITY_SYMBOLS: frozenset[str] = frozenset({
    "AAPL", "TSLA", "AMZN", "GOOG", "GOOGL", "META", "MSFT", "NVDA",
    "SPY", "QQQ", "IWM", "GLD", "TLT", "XLF", "XLE", "XLK",
    "NFLX", "AMD", "INTC", "CRM", "ORCL", "JPM", "GS", "BAC",
})

_FOREX_CURRENCIES: frozenset[str] = frozenset({
    "EUR", "GBP", "USD", "JPY", "AUD", "CAD", "CHF", "NZD",
    "SGD", "HKD", "NOK", "SEK", "DKK", "MXN", "ZAR",
})


def _infer_venue(symbol: str) -> str:
    """Best-effort venue inference from symbol format."""
    upper = symbol.upper()
    # Forex: "EUR_USD", "GBP_USD" (OANDA underscore format)
    if "_" in upper:
        parts = upper.split("_")
        if len(parts) == 2 and all(p in _FOREX_CURRENCIES for p in parts):
            return "oanda_paper"
    # Common equity tickers
    if upper in _EQUITY_SYMBOLS:
        return "alpaca_paper"
    # Default: crypto → Binance (largest liquidity)
    return "binance_paper"


class PaperTradingHub:
    """Aggregate paper trading hub for all six venue adapters.

    Construction builds all six PaperVenueAdapters in READY state.
    No external connectivity is ever attempted.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._adapters: dict[str, PaperVenueAdapter] = {
            name: PaperVenueAdapter(cfg)
            for name, cfg in VENUE_CONFIGS.items()
        }

    # ------------------------------------------------------------------
    # Signal routing
    # ------------------------------------------------------------------

    def submit(self, signal: SignalEvent, mark_price: float) -> ExecutionEvent:
        """Route a paper signal to the appropriate venue adapter.

        Routing precedence:
          1. signal.meta["paper_venue"] — explicit override
          2. Domain heuristic from symbol format
          3. Fallback to binance_paper
        """
        venue_name = (signal.meta or {}).get("paper_venue") or _infer_venue(signal.symbol)
        adapter = self._adapters.get(venue_name) or self._adapters["binance_paper"]
        return adapter.submit(signal, mark_price)

    def submit_to(
        self, venue: str, signal: SignalEvent, mark_price: float
    ) -> ExecutionEvent:
        """Submit directly to a named venue adapter."""
        adapter = self._adapters.get(venue)
        if adapter is None:
            raise ValueError(f"unknown paper venue: {venue!r}")
        return adapter.submit(signal, mark_price)

    # ------------------------------------------------------------------
    # Portfolio read surface
    # ------------------------------------------------------------------

    def adapter(self, name: str) -> PaperVenueAdapter | None:
        return self._adapters.get(name)

    def all_adapters(self) -> list[PaperVenueAdapter]:
        return list(self._adapters.values())

    def portfolio_snapshot(self, venue: str) -> dict[str, Any] | None:
        a = self._adapters.get(venue)
        return a.portfolio_snapshot() if a else None

    def snapshot(self) -> dict[str, Any]:
        """Full snapshot: all six portfolios + aggregate P&L."""
        portfolios = {
            name: adapter.portfolio_snapshot()
            for name, adapter in self._adapters.items()
        }
        return {
            "hub": "PaperTradingHub",
            "venue_count": len(portfolios),
            "portfolios": portfolios,
            "summary": self._aggregate_summary(portfolios),
        }

    def pnl_summary(self) -> dict[str, Any]:
        portfolios = {
            name: adapter.portfolio_snapshot()
            for name, adapter in self._adapters.items()
        }
        return self._aggregate_summary(portfolios)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_venue(self, venue: str) -> bool:
        """Reset one venue's paper portfolio to initial state."""
        a = self._adapters.get(venue)
        if a is None:
            return False
        a.reset()
        return True

    def reset_all(self) -> None:
        """Reset all six paper portfolios to initial state."""
        for a in self._adapters.values():
            a.reset()

    # ------------------------------------------------------------------
    # Aggregate helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_summary(portfolios: dict[str, dict[str, Any]]) -> dict[str, Any]:
        total_pnl = sum(p.get("realized_pnl", 0.0) for p in portfolios.values())
        total_initial = sum(p.get("initial_cash", 0.0) for p in portfolios.values())
        total_cash = sum(p.get("cash", 0.0) for p in portfolios.values())
        total_fills = sum(p.get("submit_count", 0) for p in portfolios.values())
        open_positions = sum(p.get("open_position_count", 0) for p in portfolios.values())
        venue_pnls = {
            name: round(p.get("realized_pnl", 0.0), 4)
            for name, p in portfolios.items()
        }
        return {
            "total_initial_capital": round(total_initial, 2),
            "total_cash": round(total_cash, 2),
            "total_realized_pnl": round(total_pnl, 4),
            "total_realized_pnl_pct": round(
                total_pnl / total_initial * 100, 4
            ) if total_initial else 0.0,
            "total_fills": total_fills,
            "total_open_positions": open_positions,
            "venue_pnl": venue_pnls,
        }


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_hub: PaperTradingHub | None = None
_hub_lock = threading.Lock()


def get_paper_trading_hub() -> PaperTradingHub:
    """Return the process-wide PaperTradingHub singleton."""
    global _hub
    with _hub_lock:
        if _hub is None:
            _hub = PaperTradingHub()
    return _hub


__all__ = ["PaperTradingHub", "get_paper_trading_hub"]
