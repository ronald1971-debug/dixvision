"""trader_modeling.profile_extractor — Extract behavioral signals from order flow.

Receives raw market ticks and order-flow features and converts them into
a typed TraderSignal — the unit of evidence that feeds into behavioral
classification.

Authority (B1): imports only from core.*, state.*, trader_modeling.*.
INV-15: ts_ns is caller-supplied; no wall-clock reads.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TraderSignal:
    """One extracted behavioral signal from order-flow data.

    All fields are normalised to [0, 1] except ``direction`` which is
    +1 (buy-side pressure) or -1 (sell-side pressure).
    """

    ts_ns: int
    symbol: str
    direction: float          # +1 buy pressure, -1 sell pressure
    aggression: float         # market-order fraction of volume
    size_rank: float          # relative size percentile in recent window
    speed: float              # trades-per-second normalised [0, 1]
    regime_alignment: float   # alignment with current market regime [0, 1]
    source: str = "order_flow"


@dataclass(frozen=True, slots=True)
class SignalBatch:
    """A batch of TraderSignals ready for classification."""

    ts_ns: int
    symbol: str
    signals: tuple[TraderSignal, ...]
    window_size: int

    @property
    def mean_aggression(self) -> float:
        if not self.signals:
            return 0.0
        return sum(s.aggression for s in self.signals) / len(self.signals)

    @property
    def mean_direction(self) -> float:
        if not self.signals:
            return 0.0
        return sum(s.direction for s in self.signals) / len(self.signals)

    @property
    def mean_speed(self) -> float:
        if not self.signals:
            return 0.0
        return sum(s.speed for s in self.signals) / len(self.signals)


class ProfileExtractor:
    """Extracts normalized behavioral signals from raw market tick data.

    Maintains a rolling window of ticks per symbol and derives the
    TraderSignals that characterize the dominant participant behavior.

    Args:
        window: number of ticks to keep per symbol for rolling stats
        min_batch: minimum signals in a batch before classification fires
    """

    def __init__(self, window: int = 200, min_batch: int = 10) -> None:
        self._window = max(10, window)
        self._min_batch = max(2, min_batch)
        self._lock = threading.Lock()
        # symbol → deque of raw tick dicts
        self._tick_buffers: dict[str, deque[dict[str, Any]]] = {}
        # symbol → deque of extracted TraderSignals
        self._signal_buffers: dict[str, deque[TraderSignal]] = {}
        self._extract_count: int = 0

    def ingest(self, tick: dict[str, Any], ts_ns: int) -> TraderSignal | None:
        """Ingest one market tick and return a TraderSignal if extractable.

        Args:
            tick: raw tick dict — expected keys: symbol, price, volume,
                  is_buyer_maker (bool), trade_count (optional)
            ts_ns: caller-supplied timestamp (INV-15)
        Returns:
            TraderSignal if extraction succeeded, else None
        """
        symbol = tick.get("symbol", "")
        if not symbol:
            return None

        with self._lock:
            if symbol not in self._tick_buffers:
                self._tick_buffers[symbol] = deque(maxlen=self._window)
                self._signal_buffers[symbol] = deque(maxlen=self._window)
            buf = self._tick_buffers[symbol]
            buf.append(tick)

            if len(buf) < 3:
                return None

            signal = self._extract_signal(symbol, tick, buf, ts_ns)
            if signal is not None:
                self._signal_buffers[symbol].append(signal)
                self._extract_count += 1
            return signal

    def get_batch(self, symbol: str, ts_ns: int) -> SignalBatch | None:
        """Return a SignalBatch for classification if enough signals exist."""
        with self._lock:
            sigs = self._signal_buffers.get(symbol)
            if not sigs or len(sigs) < self._min_batch:
                return None
            return SignalBatch(
                ts_ns=ts_ns,
                symbol=symbol,
                signals=tuple(sigs),
                window_size=len(sigs),
            )

    def symbols(self) -> list[str]:
        with self._lock:
            return list(self._tick_buffers.keys())

    @property
    def extract_count(self) -> int:
        return self._extract_count

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "extract_count": self._extract_count,
                "symbols": list(self._tick_buffers.keys()),
                "signal_counts": {
                    sym: len(sigs)
                    for sym, sigs in self._signal_buffers.items()
                },
            }

    # ------------------------------------------------------------------
    # Internal extraction logic
    # ------------------------------------------------------------------

    def _extract_signal(
        self,
        symbol: str,
        tick: dict[str, Any],
        buf: deque[dict[str, Any]],
        ts_ns: int,
    ) -> TraderSignal | None:
        try:
            price = float(tick.get("price", 0.0) or 0.0)
            volume = float(tick.get("volume", 0.0) or 0.0)
            is_buyer_maker = bool(tick.get("is_buyer_maker", False))
            if price <= 0 or volume <= 0:
                return None

            # Direction: +1 if aggressive buy (taker buy), -1 if sell
            direction = -1.0 if is_buyer_maker else 1.0

            # Aggression: fraction of volume as market orders in window
            # Proxy: is_buyer_maker=False means taker bought (aggressive)
            taker_buy_count = sum(
                1 for t in buf if not t.get("is_buyer_maker", True)
            )
            aggression = taker_buy_count / max(1, len(buf))

            # Size rank: percentile of this trade's volume in the window
            volumes = [float(t.get("volume", 0.0) or 0.0) for t in buf]
            volumes.sort()
            pos = sum(1 for v in volumes if v <= volume)
            size_rank = pos / max(1, len(volumes))

            # Speed: trades per second proxy — use reciprocal of mean gap
            # If ticks have no timestamp we use count/window as proxy
            speed_proxy = min(1.0, len(buf) / self._window)

            # Regime alignment: read from MarketState best-effort
            regime_alignment = self._regime_alignment(direction, symbol)

            return TraderSignal(
                ts_ns=ts_ns,
                symbol=symbol,
                direction=direction,
                aggression=round(aggression, 4),
                size_rank=round(size_rank, 4),
                speed=round(speed_proxy, 4),
                regime_alignment=round(regime_alignment, 4),
            )
        except Exception:
            return None

    @staticmethod
    def _regime_alignment(direction: float, symbol: str) -> float:
        """Estimate alignment between participant direction and market regime."""
        try:
            from state.market_state import get_market_state
            ms = get_market_state()
            regime = ms.regime()
            if regime == "BULL":
                return 0.5 + 0.4 * direction   # buy-aligned in bull
            if regime == "BEAR":
                return 0.5 - 0.4 * direction   # sell-aligned in bear
            return 0.5  # neutral in mixed
        except Exception:
            return 0.5


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_extractor: ProfileExtractor | None = None
_extractor_lock = threading.Lock()


def get_profile_extractor(window: int = 200) -> ProfileExtractor:
    """Return the process-wide ProfileExtractor singleton."""
    global _extractor
    with _extractor_lock:
        if _extractor is None:
            _extractor = ProfileExtractor(window=window)
    return _extractor


__all__ = [
    "ProfileExtractor",
    "SignalBatch",
    "TraderSignal",
    "get_profile_extractor",
]
