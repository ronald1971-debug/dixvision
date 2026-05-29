"""MarketState — last-known-value cache for live market prices (P3 Reality Layer).

Single process-wide store of the most recent price for each symbol that has
been ingested.  Written by the IngestionBus on every arriving tick; read by
EnvironmentAwareness to inject real market context into INDIRA's autonomous
thought cycles.

Design:
    * Thread-safe LKV cache: one entry per symbol, overwritten on each tick.
    * Trend detection: compares the last two prices for each symbol and
      labels the move as "up" / "dn" / "flat".
    * Volatility heuristic: rolling 20-tick range / midpoint per symbol.
    * Regime heuristic: if >60% of tracked symbols are "up" → BULL, >60%
      are "dn" → BEAR, else MIXED.  Basis for INDIRA's market awareness.
    * PAPER-mode safe: if no ticks have arrived, all probes return graceful
      defaults ("no_data") rather than crashing.

Authority: pure state tier — no engine, no runtime, no intelligence imports.
INV-15: ts_ns is embedded in every PriceTick by the ingestion bus (caller-supplied).
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# PriceTick — one price observation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PriceTick:
    """One normalized price observation from the ingestion bus."""

    symbol: str
    price: float
    volume: float
    source: str   # "alpaca" | "binance" | "paper" | ...
    ts_ns: int


# ---------------------------------------------------------------------------
# SymbolState — per-symbol LKV + rolling window
# ---------------------------------------------------------------------------

_WINDOW = 20   # rolling price window for volatility calculation


@dataclass
class SymbolState:
    latest: PriceTick
    prev_price: float
    window: deque   # deque[float]

    def trend(self) -> str:
        delta = self.latest.price - self.prev_price
        if delta > self.prev_price * 0.0005:
            return "up"
        if delta < -self.prev_price * 0.0005:
            return "dn"
        return "flat"

    def volatility(self) -> float:
        """Normalised range: (max - min) / mid over the rolling window."""
        prices = list(self.window)
        if len(prices) < 2:
            return 0.0
        lo, hi = min(prices), max(prices)
        mid = (lo + hi) / 2
        return (hi - lo) / mid if mid > 0 else 0.0


# ---------------------------------------------------------------------------
# MarketState
# ---------------------------------------------------------------------------


class MarketState:
    """Process-wide last-known-value market price cache.

    Updated by the IngestionBus on every arriving tick.  Read by
    EnvironmentAwareness to build INDIRA's live market context.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._symbols: dict[str, SymbolState] = {}
        self._tick_count = 0
        self._last_ts_ns: int = 0

    # ------------------------------------------------------------------
    # Write path (called from IngestionBus)
    # ------------------------------------------------------------------

    def update(self, tick: PriceTick) -> None:
        """Update state with one new price tick."""
        with self._lock:
            existing = self._symbols.get(tick.symbol)
            if existing is None:
                window: deque = deque(maxlen=_WINDOW)
                window.append(tick.price)
                self._symbols[tick.symbol] = SymbolState(
                    latest=tick,
                    prev_price=tick.price,
                    window=window,
                )
            else:
                existing.prev_price = existing.latest.price
                existing.latest = tick
                existing.window.append(tick.price)
            self._tick_count += 1
            self._last_ts_ns = tick.ts_ns
        self._publish(tick)

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def latest_price(self, symbol: str) -> float | None:
        with self._lock:
            s = self._symbols.get(symbol)
            return s.latest.price if s else None

    def active_symbols(self) -> list[str]:
        with self._lock:
            return sorted(self._symbols.keys())

    def regime(self) -> str:
        """Broad market regime heuristic from symbol trend consensus."""
        with self._lock:
            if not self._symbols:
                return "no_data"
            trends = [s.trend() for s in self._symbols.values()]
        up = trends.count("up")
        dn = trends.count("dn")
        n = len(trends)
        if up / n > 0.60:
            return "BULL"
        if dn / n > 0.60:
            return "BEAR"
        return "MIXED"

    def volatility_label(self) -> str:
        """Aggregate volatility label from all symbol windows."""
        with self._lock:
            if not self._symbols:
                return "no_data"
            vols = [s.volatility() for s in self._symbols.values()]
        avg = sum(vols) / len(vols)
        if avg > 0.02:
            return "HIGH"
        if avg > 0.005:
            return "MED"
        return "LOW"

    def format_for_context(self, max_symbols: int = 3) -> str:
        """Compact key=value string for EnvironmentAwareness context.

        Returns empty string when no ticks have arrived (PAPER mode, no feed).
        """
        with self._lock:
            if not self._symbols:
                return ""
            symbols = list(self._symbols.items())[:max_symbols]

        parts = []
        for sym, state in symbols:
            price = state.latest.price
            trend = state.trend()
            short = sym.replace("/USD", "").replace("/USDT", "").replace("USD", "")
            parts.append(f"{short}={price:.1f}({trend})")

        regime = self.regime()
        vol = self.volatility_label()
        parts.append(f"regime={regime}")
        parts.append(f"vol={vol}")
        return " ".join(parts)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            syms = {
                sym: {
                    "price": s.latest.price,
                    "trend": s.trend(),
                    "vol": round(s.volatility(), 4),
                    "source": s.latest.source,
                    "ts_ns": s.latest.ts_ns,
                }
                for sym, s in self._symbols.items()
            }
        return {
            "tick_count": self._tick_count,
            "last_ts_ns": self._last_ts_ns,
            "regime": self.regime(),
            "volatility": self.volatility_label(),
            "symbols": syms,
        }

    # ------------------------------------------------------------------
    # Event bus publishing
    # ------------------------------------------------------------------

    @staticmethod
    def _publish(tick: PriceTick) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(
                CognitiveChannel.MARKET_TICK,   # type: ignore[attr-defined]
                {
                    "symbol": tick.symbol,
                    "price": tick.price,
                    "volume": tick.volume,
                    "source": tick.source,
                    "ts_ns": tick.ts_ns,
                },
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_state: MarketState | None = None
_state_lock = threading.Lock()


def get_market_state() -> MarketState:
    """Return the process-wide MarketState singleton."""
    global _state
    with _state_lock:
        if _state is None:
            _state = MarketState()
    return _state


__all__ = [
    "MarketState",
    "PriceTick",
    "get_market_state",
]
