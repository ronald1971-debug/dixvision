"""execution_engine/market_data/book_builder.py
DIX VISION v42.2 — Order Book Builder

Incrementally maintains L2 order book state from streaming delta updates.
Handles full snapshots (replaces state) and delta updates (add/modify/delete
price levels). Produces NormalizedBook snapshots on demand.

Thread-safe. Pure state management — no IO, no clock reads in core logic.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from execution_engine.market_data.normalizer import NormalizedBook, NormalizedLevel


@dataclass(frozen=True, slots=True)
class BookDelta:
    """A single incremental order book update."""
    symbol: str
    exchange: str
    side: str          # BID | ASK
    price: float
    qty: float         # 0.0 = delete this level
    ts_ns: int


class OrderBookState:
    """
    Mutable L2 book state for one symbol on one exchange.

    Not thread-safe on its own — callers use BookBuilder's lock.
    """

    def __init__(self, symbol: str, exchange: str) -> None:
        self.symbol = symbol
        self.exchange = exchange
        self._bids: dict[float, float] = {}   # price → qty
        self._asks: dict[float, float] = {}
        self._last_ts_ns: int = 0
        self._update_count: int = 0

    def apply_snapshot(
        self,
        bids: list[list[float]],
        asks: list[list[float]],
        ts_ns: int,
    ) -> None:
        self._bids = {float(p): float(q) for p, q in bids}
        self._asks = {float(p): float(q) for p, q in asks}
        self._last_ts_ns = ts_ns
        self._update_count += 1

    def apply_delta(self, delta: BookDelta) -> None:
        book = self._bids if delta.side.upper() == "BID" else self._asks
        if delta.qty <= 0.0:
            book.pop(delta.price, None)
        else:
            book[delta.price] = delta.qty
        self._last_ts_ns = delta.ts_ns
        self._update_count += 1

    def to_normalized(self, depth: int = 20) -> NormalizedBook:
        sorted_bids = sorted(self._bids.items(), reverse=True)[:depth]
        sorted_asks = sorted(self._asks.items())[:depth]
        return NormalizedBook(
            symbol=self.symbol,
            exchange=self.exchange,
            bids=tuple(NormalizedLevel(p, q) for p, q in sorted_bids),
            asks=tuple(NormalizedLevel(p, q) for p, q in sorted_asks),
            ts_ns=self._last_ts_ns,
        )


class BookBuilder:
    """
    Manages incremental L2 order book state for multiple symbols.

    Thread-safe. Callers apply snapshots and deltas; read snapshots
    of the current book state at any time.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._books: dict[tuple[str, str], OrderBookState] = {}

    def _key(self, symbol: str, exchange: str) -> tuple[str, str]:
        return (symbol, exchange)

    def apply_snapshot(
        self,
        symbol: str,
        exchange: str,
        bids: list[list[float]],
        asks: list[list[float]],
        ts_ns: int,
    ) -> NormalizedBook:
        key = self._key(symbol, exchange)
        with self._lock:
            if key not in self._books:
                self._books[key] = OrderBookState(symbol, exchange)
            book = self._books[key]
            book.apply_snapshot(bids, asks, ts_ns)
            return book.to_normalized()

    def apply_delta(self, delta: BookDelta) -> NormalizedBook | None:
        key = self._key(delta.symbol, delta.exchange)
        with self._lock:
            book = self._books.get(key)
            if book is None:
                return None
            book.apply_delta(delta)
            return book.to_normalized()

    def get_book(
        self,
        symbol: str,
        exchange: str,
        depth: int = 20,
    ) -> NormalizedBook | None:
        key = self._key(symbol, exchange)
        with self._lock:
            book = self._books.get(key)
            if book is None:
                return None
            return book.to_normalized(depth)

    def symbols(self) -> list[tuple[str, str]]:
        with self._lock:
            return list(self._books.keys())

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"book_count": len(self._books)}


__all__ = ["BookBuilder", "BookDelta", "OrderBookState"]
