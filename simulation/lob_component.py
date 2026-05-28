# ADAPTED FROM: dyn-trding/PyLOB
# (PyLOB/LimitOrderBook.py — bid/ask price levels, queue management, fill matching)
"""C-45 — Pure Python Limit Order Book component for simulation.

This module adapts PyLOB (https://github.com/dyn-trding/PyLOB,
MIT License) as a LOB component inside the simulation tier. It drives
``simulation.flash_crash_synth`` and provides the order-matching engine
for adversarial scenario simulation.

What survives from upstream:

* PyLOB's **price-level queue structure**: bid/ask sides maintain
  sorted price levels, each level holds a FIFO queue of resting orders.
* **Fill matching logic**: incoming market orders walk the opposite
  book, matching against resting limits in price-time priority.
* **Price-level management**: empty levels are removed; new levels are
  inserted in sort order.

DIX integration rules:

* OFFLINE simulation tier only. No IO, no clock reads, no network.
* Accepts ``seed`` for any stochastic components (order arrival).
* Fully deterministic: same order sequence → same fills, same book state.
* INV-15: byte-identical replay guaranteed.
* No PyLOB import at runtime — algorithm is reproduced in pure Python.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections import deque
from typing import Final

LOB_VERSION: Final[str] = "c-45.v1"

# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class Order:
    """A single limit or market order.

    Attributes:
        order_id: Unique order identifier.
        ts_ns: Submission timestamp (nanoseconds).
        side: "BID" or "ASK".
        price: Limit price (0.0 for market orders).
        qty: Order quantity (remaining unfilled).
        is_market: Whether this is a market order.
    """

    order_id: str
    ts_ns: int
    side: str
    price: float
    qty: float
    is_market: bool = False

    def __post_init__(self) -> None:
        if self.side not in ("BID", "ASK"):
            raise LOBError(f"side must be BID or ASK, got {self.side!r}")
        if self.qty <= 0:
            raise LOBError(f"qty must be > 0, got {self.qty}")
        if not self.is_market and self.price <= 0:
            raise LOBError(f"limit order price must be > 0, got {self.price}")


@dataclasses.dataclass(frozen=True, slots=True)
class Fill:
    """Record of a matched fill between two orders.

    Attributes:
        fill_id: Unique fill identifier.
        ts_ns: Fill timestamp.
        price: Execution price.
        qty: Filled quantity.
        aggressor_id: Incoming (taker) order ID.
        resting_id: Resting (maker) order ID.
        side: Side of the aggressor.
    """

    fill_id: str
    ts_ns: int
    price: float
    qty: float
    aggressor_id: str
    resting_id: str
    side: str


@dataclasses.dataclass(frozen=True, slots=True)
class BookSnapshot:
    """Point-in-time snapshot of the order book.

    Attributes:
        ts_ns: Snapshot timestamp.
        bids: Sorted bid levels (price descending) with aggregated qty.
        asks: Sorted ask levels (price ascending) with aggregated qty.
        spread: Bid-ask spread (0 if book is empty on either side).
        mid_price: Midpoint price (0 if book is empty on either side).
        n_fills: Total fills generated so far.
        digest: BLAKE2b digest for replay verification.
    """

    ts_ns: int
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]
    spread: float
    mid_price: float
    n_fills: int
    digest: str


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LOBError(ValueError):
    """Base class for LOB-related errors."""


# ---------------------------------------------------------------------------
# Price level (internal mutable structure)
# ---------------------------------------------------------------------------


class _PriceLevel:
    """A single price level holding a FIFO queue of resting orders."""

    __slots__ = ("price", "orders", "total_qty")

    def __init__(self, price: float) -> None:
        self.price = price
        self.orders: deque[list[str, float]] = deque()  # type: ignore[type-arg]
        self.total_qty = 0.0

    def add_order(self, order_id: str, qty: float) -> None:
        self.orders.append([order_id, qty])
        self.total_qty += qty

    def is_empty(self) -> bool:
        return self.total_qty <= 0.0 or not self.orders


# ---------------------------------------------------------------------------
# Limit Order Book
# ---------------------------------------------------------------------------


class LimitOrderBook:
    """Pure Python Limit Order Book with price-time priority matching.

    This class mirrors PyLOB's LimitOrderBook but with no external
    dependencies. Orders are matched on price-time priority: best price
    first, then FIFO within each price level.

    Args:
        symbol: Trading symbol/instrument identifier.
    """

    def __init__(self, symbol: str = "SIM") -> None:
        self._symbol = symbol
        self._bids: list[_PriceLevel] = []  # sorted descending by price
        self._asks: list[_PriceLevel] = []  # sorted ascending by price
        self._fills: list[Fill] = []
        self._fill_counter = 0
        self._order_map: dict[str, tuple[str, float]] = {}  # order_id → (side, price)

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def best_bid(self) -> float | None:
        """Best (highest) bid price, or None if bid book empty."""
        for level in self._bids:
            if not level.is_empty():
                return level.price
        return None

    @property
    def best_ask(self) -> float | None:
        """Best (lowest) ask price, or None if ask book empty."""
        for level in self._asks:
            if not level.is_empty():
                return level.price
        return None

    @property
    def spread(self) -> float:
        """Current bid-ask spread (0 if one side empty)."""
        bb = self.best_bid
        ba = self.best_ask
        if bb is None or ba is None:
            return 0.0
        return ba - bb

    @property
    def mid_price(self) -> float:
        """Midpoint price (0 if one side empty)."""
        bb = self.best_bid
        ba = self.best_ask
        if bb is None or ba is None:
            return 0.0
        return (bb + ba) / 2.0

    @property
    def n_fills(self) -> int:
        return len(self._fills)

    @property
    def fills(self) -> tuple[Fill, ...]:
        return tuple(self._fills)

    def submit_order(self, order: Order) -> list[Fill]:
        """Submit an order to the book. Returns any fills generated.

        Market orders immediately match against the opposite side.
        Limit orders first attempt to match (if marketable), then
        any remaining quantity rests on the book.
        """
        if order.is_market:
            return self._execute_market_order(order)
        return self._execute_limit_order(order)

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a resting order by ID. Returns True if found and cancelled."""
        if order_id not in self._order_map:
            return False
        side, price = self._order_map[order_id]
        levels = self._bids if side == "BID" else self._asks
        for level in levels:
            if level.price == price:
                for i, (oid, qty) in enumerate(level.orders):
                    if oid == order_id:
                        level.orders.remove(level.orders[i])
                        level.total_qty -= qty
                        del self._order_map[order_id]
                        return True
        return False

    def snapshot(self, ts_ns: int) -> BookSnapshot:
        """Take a point-in-time snapshot of the book state."""
        bids = tuple((lvl.price, lvl.total_qty) for lvl in self._bids if not lvl.is_empty())
        asks = tuple((lvl.price, lvl.total_qty) for lvl in self._asks if not lvl.is_empty())
        digest = self._compute_digest(ts_ns)
        return BookSnapshot(
            ts_ns=ts_ns,
            bids=bids,
            asks=asks,
            spread=self.spread,
            mid_price=self.mid_price,
            n_fills=self.n_fills,
            digest=digest,
        )

    def _compute_digest(self, ts_ns: int) -> str:
        h = hashlib.blake2b(digest_size=16)
        h.update(ts_ns.to_bytes(8, "little"))
        h.update(self.n_fills.to_bytes(4, "little"))
        bb = self.best_bid or 0.0
        ba = self.best_ask or 0.0
        h.update(bb.hex().encode())
        h.update(ba.hex().encode())
        return h.hexdigest()

    def _find_or_create_bid_level(self, price: float) -> _PriceLevel:
        """Find or insert a bid price level (descending order)."""
        for i, level in enumerate(self._bids):
            if level.price == price:
                return level
            if level.price < price:
                new_level = _PriceLevel(price)
                self._bids.insert(i, new_level)
                return new_level
        new_level = _PriceLevel(price)
        self._bids.append(new_level)
        return new_level

    def _find_or_create_ask_level(self, price: float) -> _PriceLevel:
        """Find or insert an ask price level (ascending order)."""
        for i, level in enumerate(self._asks):
            if level.price == price:
                return level
            if level.price > price:
                new_level = _PriceLevel(price)
                self._asks.insert(i, new_level)
                return new_level
        new_level = _PriceLevel(price)
        self._asks.append(new_level)
        return new_level

    def _execute_market_order(self, order: Order) -> list[Fill]:
        """Execute a market order against the opposite side."""
        fills: list[Fill] = []
        remaining = order.qty
        opposite = self._asks if order.side == "BID" else self._bids

        for level in list(opposite):
            if remaining <= 0:
                break
            while level.orders and remaining > 0:
                resting = level.orders[0]
                resting_id, resting_qty = resting[0], resting[1]
                fill_qty = min(remaining, resting_qty)

                self._fill_counter += 1
                fill = Fill(
                    fill_id=f"F-{self._fill_counter}",
                    ts_ns=order.ts_ns,
                    price=level.price,
                    qty=fill_qty,
                    aggressor_id=order.order_id,
                    resting_id=resting_id,
                    side=order.side,
                )
                fills.append(fill)
                self._fills.append(fill)

                remaining -= fill_qty
                resting[1] -= fill_qty
                level.total_qty -= fill_qty

                if resting[1] <= 0:
                    level.orders.popleft()
                    if resting_id in self._order_map:
                        del self._order_map[resting_id]

        # Clean up empty levels
        if order.side == "BID":
            self._asks = [lv for lv in self._asks if not lv.is_empty()]
        else:
            self._bids = [lv for lv in self._bids if not lv.is_empty()]

        return fills

    def _execute_limit_order(self, order: Order) -> list[Fill]:
        """Execute a limit order: match if marketable, then rest remainder."""
        fills: list[Fill] = []
        remaining = order.qty

        # Check if the limit order is marketable (crosses the spread)
        if order.side == "BID":
            # Bid crosses if price >= best ask
            while remaining > 0 and self._asks:
                best_ask_level = self._asks[0]
                if best_ask_level.is_empty():
                    self._asks.pop(0)
                    continue
                if order.price < best_ask_level.price:
                    break
                # Match
                while best_ask_level.orders and remaining > 0:
                    resting = best_ask_level.orders[0]
                    resting_id, resting_qty = resting[0], resting[1]
                    fill_qty = min(remaining, resting_qty)

                    self._fill_counter += 1
                    fill = Fill(
                        fill_id=f"F-{self._fill_counter}",
                        ts_ns=order.ts_ns,
                        price=best_ask_level.price,
                        qty=fill_qty,
                        aggressor_id=order.order_id,
                        resting_id=resting_id,
                        side=order.side,
                    )
                    fills.append(fill)
                    self._fills.append(fill)

                    remaining -= fill_qty
                    resting[1] -= fill_qty
                    best_ask_level.total_qty -= fill_qty

                    if resting[1] <= 0:
                        best_ask_level.orders.popleft()
                        if resting_id in self._order_map:
                            del self._order_map[resting_id]

                if best_ask_level.is_empty():
                    self._asks.pop(0)
        else:
            # Ask crosses if price <= best bid
            while remaining > 0 and self._bids:
                best_bid_level = self._bids[0]
                if best_bid_level.is_empty():
                    self._bids.pop(0)
                    continue
                if order.price > best_bid_level.price:
                    break
                while best_bid_level.orders and remaining > 0:
                    resting = best_bid_level.orders[0]
                    resting_id, resting_qty = resting[0], resting[1]
                    fill_qty = min(remaining, resting_qty)

                    self._fill_counter += 1
                    fill = Fill(
                        fill_id=f"F-{self._fill_counter}",
                        ts_ns=order.ts_ns,
                        price=best_bid_level.price,
                        qty=fill_qty,
                        aggressor_id=order.order_id,
                        resting_id=resting_id,
                        side=order.side,
                    )
                    fills.append(fill)
                    self._fills.append(fill)

                    remaining -= fill_qty
                    resting[1] -= fill_qty
                    best_bid_level.total_qty -= fill_qty

                    if resting[1] <= 0:
                        best_bid_level.orders.popleft()
                        if resting_id in self._order_map:
                            del self._order_map[resting_id]

                if best_bid_level.is_empty():
                    self._bids.pop(0)

        # Rest any remaining quantity
        if remaining > 0:
            if order.side == "BID":
                level = self._find_or_create_bid_level(order.price)
            else:
                level = self._find_or_create_ask_level(order.price)
            level.add_order(order.order_id, remaining)
            self._order_map[order.order_id] = (order.side, order.price)

        return fills


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


__all__ = [
    "BookSnapshot",
    "Fill",
    "LOB_VERSION",
    "LOBError",
    "LimitOrderBook",
    "Order",
]
