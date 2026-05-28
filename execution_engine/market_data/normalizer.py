"""execution_engine/market_data/normalizer.py
DIX VISION v42.2 — Market Data Normalizer

Converts raw exchange tick/orderbook/trade payloads into canonical
NormalizedTick and NormalizedBook value objects. All timestamp fields
are normalised to nanoseconds; price/qty fields are floats.

Pure functions + frozen dataclasses (INV-15 replay determinism).
No IO, no clock reads. Callers supply ts_ns explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NormalizedTick:
    """Canonical single-price tick."""
    symbol: str
    exchange: str
    bid: float
    ask: float
    last: float
    volume: float
    ts_ns: int


@dataclass(frozen=True, slots=True)
class NormalizedLevel:
    """Single price level in a normalized order book."""
    price: float
    qty: float


@dataclass(frozen=True, slots=True)
class NormalizedBook:
    """Canonical L2 order book snapshot."""
    symbol: str
    exchange: str
    bids: tuple[NormalizedLevel, ...]
    asks: tuple[NormalizedLevel, ...]
    ts_ns: int

    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 0.0

    @property
    def mid(self) -> float:
        if self.bids and self.asks:
            return (self.bids[0].price + self.asks[0].price) / 2.0
        return 0.0

    @property
    def spread(self) -> float:
        if self.bids and self.asks:
            return self.asks[0].price - self.bids[0].price
        return 0.0


@dataclass(frozen=True, slots=True)
class NormalizedTrade:
    """Canonical executed trade."""
    symbol: str
    exchange: str
    side: str        # BUY | SELL
    price: float
    qty: float
    trade_id: str
    ts_ns: int


class MarketDataNormalizer:
    """
    Converts raw exchange payloads to canonical value objects.

    Stateless — all methods are pure functions on the instance.
    Exchange-specific adapters call normalize_* then publish the result.
    """

    def __init__(self, exchange: str) -> None:
        self._exchange = exchange

    def normalize_tick(
        self,
        symbol: str,
        raw: dict[str, Any],
        ts_ns: int,
    ) -> NormalizedTick:
        """Normalize a raw tick payload."""
        return NormalizedTick(
            symbol=symbol,
            exchange=self._exchange,
            bid=float(raw.get("bid", raw.get("b", 0.0))),
            ask=float(raw.get("ask", raw.get("a", 0.0))),
            last=float(raw.get("last", raw.get("c", raw.get("price", 0.0)))),
            volume=float(raw.get("volume", raw.get("v", 0.0))),
            ts_ns=ts_ns,
        )

    def normalize_book(
        self,
        symbol: str,
        raw_bids: list[list[float]],
        raw_asks: list[list[float]],
        ts_ns: int,
        depth: int = 20,
    ) -> NormalizedBook:
        """Normalize raw bids/asks lists (each entry: [price, qty])."""
        bids = tuple(
            NormalizedLevel(price=float(p), qty=float(q))
            for p, q in raw_bids[:depth]
        )
        asks = tuple(
            NormalizedLevel(price=float(p), qty=float(q))
            for p, q in raw_asks[:depth]
        )
        return NormalizedBook(
            symbol=symbol,
            exchange=self._exchange,
            bids=bids,
            asks=asks,
            ts_ns=ts_ns,
        )

    def normalize_trade(
        self,
        symbol: str,
        raw: dict[str, Any],
        ts_ns: int,
    ) -> NormalizedTrade:
        """Normalize a raw public trade."""
        side_raw = str(raw.get("side", raw.get("m", "buy")))
        side = "SELL" if side_raw.lower() in ("sell", "s", "false") else "BUY"
        return NormalizedTrade(
            symbol=symbol,
            exchange=self._exchange,
            side=side,
            price=float(raw.get("price", raw.get("p", 0.0))),
            qty=float(raw.get("qty", raw.get("q", raw.get("size", 0.0)))),
            trade_id=str(raw.get("id", raw.get("trade_id", ""))),
            ts_ns=ts_ns,
        )


__all__ = [
    "MarketDataNormalizer",
    "NormalizedBook",
    "NormalizedLevel",
    "NormalizedTick",
    "NormalizedTrade",
]
