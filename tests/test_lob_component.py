"""Tests for C-45 — PyLOB Limit Order Book component.

Coverage:
* Order validation
* Limit order resting
* Market order matching (full and partial fills)
* Price-time priority
* Bid-ask spread calculation
* Limit order crossing (marketable limits)
* Cancel order
* Book snapshot + INV-15 replay determinism
* Empty book edge cases
"""

from __future__ import annotations

import pytest

from simulation.lob_component import (
    LimitOrderBook,
    LOBError,
    Order,
)

# ---------------------------------------------------------------------------
# Order validation
# ---------------------------------------------------------------------------


class TestOrderValidation:
    def test_invalid_side_rejected(self) -> None:
        with pytest.raises(LOBError, match="side"):
            Order(order_id="O1", ts_ns=1, side="INVALID", price=100.0, qty=10.0)

    def test_zero_qty_rejected(self) -> None:
        with pytest.raises(LOBError, match="qty"):
            Order(order_id="O1", ts_ns=1, side="BID", price=100.0, qty=0.0)

    def test_negative_price_for_limit_rejected(self) -> None:
        with pytest.raises(LOBError, match="price"):
            Order(order_id="O1", ts_ns=1, side="BID", price=-1.0, qty=10.0)

    def test_market_order_zero_price_ok(self) -> None:
        o = Order(order_id="O1", ts_ns=1, side="BID", price=0.0, qty=10.0, is_market=True)
        assert o.is_market


# ---------------------------------------------------------------------------
# Limit orders resting
# ---------------------------------------------------------------------------


class TestLimitOrders:
    def test_bid_rests_on_empty_book(self) -> None:
        lob = LimitOrderBook()
        order = Order(order_id="B1", ts_ns=1, side="BID", price=100.0, qty=5.0)
        fills = lob.submit_order(order)
        assert fills == []
        assert lob.best_bid == 100.0
        assert lob.best_ask is None

    def test_ask_rests_on_empty_book(self) -> None:
        lob = LimitOrderBook()
        order = Order(order_id="A1", ts_ns=1, side="ASK", price=101.0, qty=5.0)
        fills = lob.submit_order(order)
        assert fills == []
        assert lob.best_ask == 101.0
        assert lob.best_bid is None

    def test_multiple_bids_sorted_descending(self) -> None:
        lob = LimitOrderBook()
        lob.submit_order(Order(order_id="B1", ts_ns=1, side="BID", price=99.0, qty=5.0))
        lob.submit_order(Order(order_id="B2", ts_ns=2, side="BID", price=100.0, qty=3.0))
        lob.submit_order(Order(order_id="B3", ts_ns=3, side="BID", price=98.0, qty=7.0))
        assert lob.best_bid == 100.0

    def test_multiple_asks_sorted_ascending(self) -> None:
        lob = LimitOrderBook()
        lob.submit_order(Order(order_id="A1", ts_ns=1, side="ASK", price=103.0, qty=5.0))
        lob.submit_order(Order(order_id="A2", ts_ns=2, side="ASK", price=101.0, qty=3.0))
        lob.submit_order(Order(order_id="A3", ts_ns=3, side="ASK", price=102.0, qty=7.0))
        assert lob.best_ask == 101.0


# ---------------------------------------------------------------------------
# Market order matching
# ---------------------------------------------------------------------------


class TestMarketOrders:
    def test_market_buy_fills_against_asks(self) -> None:
        lob = LimitOrderBook()
        lob.submit_order(Order(order_id="A1", ts_ns=1, side="ASK", price=101.0, qty=10.0))
        fills = lob.submit_order(
            Order(order_id="M1", ts_ns=2, side="BID", price=0.0, qty=5.0, is_market=True)
        )
        assert len(fills) == 1
        assert fills[0].qty == 5.0
        assert fills[0].price == 101.0
        assert fills[0].aggressor_id == "M1"
        assert fills[0].resting_id == "A1"

    def test_market_sell_fills_against_bids(self) -> None:
        lob = LimitOrderBook()
        lob.submit_order(Order(order_id="B1", ts_ns=1, side="BID", price=99.0, qty=10.0))
        fills = lob.submit_order(
            Order(order_id="M1", ts_ns=2, side="ASK", price=0.0, qty=3.0, is_market=True)
        )
        assert len(fills) == 1
        assert fills[0].qty == 3.0
        assert fills[0].price == 99.0

    def test_market_order_walks_multiple_levels(self) -> None:
        lob = LimitOrderBook()
        lob.submit_order(Order(order_id="A1", ts_ns=1, side="ASK", price=101.0, qty=3.0))
        lob.submit_order(Order(order_id="A2", ts_ns=2, side="ASK", price=102.0, qty=5.0))
        fills = lob.submit_order(
            Order(order_id="M1", ts_ns=3, side="BID", price=0.0, qty=7.0, is_market=True)
        )
        assert len(fills) == 2
        assert fills[0].qty == 3.0
        assert fills[0].price == 101.0
        assert fills[1].qty == 4.0
        assert fills[1].price == 102.0

    def test_partial_fill_leaves_remainder(self) -> None:
        lob = LimitOrderBook()
        lob.submit_order(Order(order_id="A1", ts_ns=1, side="ASK", price=101.0, qty=10.0))
        lob.submit_order(
            Order(order_id="M1", ts_ns=2, side="BID", price=0.0, qty=4.0, is_market=True)
        )
        # 6 units should remain on ask side
        snap = lob.snapshot(ts_ns=3)
        assert len(snap.asks) == 1
        assert snap.asks[0] == (101.0, 6.0)


# ---------------------------------------------------------------------------
# Price-time priority
# ---------------------------------------------------------------------------


class TestPriceTimePriority:
    def test_fifo_within_same_price(self) -> None:
        lob = LimitOrderBook()
        lob.submit_order(Order(order_id="A1", ts_ns=1, side="ASK", price=101.0, qty=5.0))
        lob.submit_order(Order(order_id="A2", ts_ns=2, side="ASK", price=101.0, qty=5.0))
        fills = lob.submit_order(
            Order(order_id="M1", ts_ns=3, side="BID", price=0.0, qty=3.0, is_market=True)
        )
        assert fills[0].resting_id == "A1"  # First in, first matched


# ---------------------------------------------------------------------------
# Crossing (marketable) limit orders
# ---------------------------------------------------------------------------


class TestCrossingLimits:
    def test_bid_crossing_ask_generates_fill(self) -> None:
        lob = LimitOrderBook()
        lob.submit_order(Order(order_id="A1", ts_ns=1, side="ASK", price=100.0, qty=5.0))
        fills = lob.submit_order(Order(order_id="B1", ts_ns=2, side="BID", price=101.0, qty=3.0))
        assert len(fills) == 1
        assert fills[0].price == 100.0
        assert fills[0].qty == 3.0

    def test_ask_crossing_bid_generates_fill(self) -> None:
        lob = LimitOrderBook()
        lob.submit_order(Order(order_id="B1", ts_ns=1, side="BID", price=100.0, qty=5.0))
        fills = lob.submit_order(Order(order_id="A1", ts_ns=2, side="ASK", price=99.0, qty=3.0))
        assert len(fills) == 1
        assert fills[0].price == 100.0
        assert fills[0].qty == 3.0

    def test_partial_crossing_rests_remainder(self) -> None:
        lob = LimitOrderBook()
        lob.submit_order(Order(order_id="A1", ts_ns=1, side="ASK", price=100.0, qty=3.0))
        fills = lob.submit_order(Order(order_id="B1", ts_ns=2, side="BID", price=101.0, qty=7.0))
        assert len(fills) == 1
        assert fills[0].qty == 3.0
        # Remaining 4 units should rest as a bid
        assert lob.best_bid == 101.0


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


class TestCancel:
    def test_cancel_existing_order(self) -> None:
        lob = LimitOrderBook()
        lob.submit_order(Order(order_id="B1", ts_ns=1, side="BID", price=100.0, qty=5.0))
        assert lob.cancel_order("B1") is True
        assert lob.best_bid is None

    def test_cancel_nonexistent_returns_false(self) -> None:
        lob = LimitOrderBook()
        assert lob.cancel_order("NOPE") is False


# ---------------------------------------------------------------------------
# Spread and mid price
# ---------------------------------------------------------------------------


class TestSpreadMid:
    def test_spread_calculation(self) -> None:
        lob = LimitOrderBook()
        lob.submit_order(Order(order_id="B1", ts_ns=1, side="BID", price=99.0, qty=5.0))
        lob.submit_order(Order(order_id="A1", ts_ns=2, side="ASK", price=101.0, qty=5.0))
        assert lob.spread == 2.0
        assert lob.mid_price == 100.0

    def test_empty_book_spread_zero(self) -> None:
        lob = LimitOrderBook()
        assert lob.spread == 0.0
        assert lob.mid_price == 0.0


# ---------------------------------------------------------------------------
# Snapshot + INV-15
# ---------------------------------------------------------------------------


class TestSnapshot:
    def test_snapshot_captures_state(self) -> None:
        lob = LimitOrderBook()
        lob.submit_order(Order(order_id="B1", ts_ns=1, side="BID", price=99.0, qty=5.0))
        lob.submit_order(Order(order_id="A1", ts_ns=2, side="ASK", price=101.0, qty=3.0))
        snap = lob.snapshot(ts_ns=100)
        assert snap.ts_ns == 100
        assert len(snap.bids) == 1
        assert len(snap.asks) == 1
        assert snap.spread == 2.0

    def test_replay_determinism(self) -> None:
        """Same order sequence → identical snapshots."""
        digests = []
        for _ in range(3):
            lob = LimitOrderBook()
            lob.submit_order(Order(order_id="B1", ts_ns=1, side="BID", price=99.0, qty=10.0))
            lob.submit_order(Order(order_id="A1", ts_ns=2, side="ASK", price=101.0, qty=8.0))
            lob.submit_order(
                Order(order_id="M1", ts_ns=3, side="BID", price=0.0, qty=5.0, is_market=True)
            )
            snap = lob.snapshot(ts_ns=4)
            digests.append(snap.digest)
        assert digests[0] == digests[1] == digests[2]
