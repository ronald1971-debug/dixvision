"""Tests for C-46 — JAX-LOB vectorized LOB simulation.

Coverage:
* Book state creation
* Limit order add
* Market order matching
* Cancel order
* Price-time priority (matches JAX-LOB __get_top_bid/ask_order_idx)
* Batch message processing (scan_through_entire_array pattern)
* Parallel book execution (simulated vmap)
* L2 snapshot
* INV-15 replay determinism
"""

from __future__ import annotations

import pytest

from simulation.adversarial.jax_lob_sim import (
    MSG_CANCEL,
    MSG_LIMIT,
    MSG_MARKET,
    SIDE_ASK,
    SIDE_BID,
    JaxLobSimError,
    OrderMessage,
    compute_state_digest,
    get_best_ask,
    get_best_bid,
    get_l2_snapshot,
    make_book_state,
    process_message,
    process_message_batch,
    run_parallel_books,
)


def _limit_bid(price: int, qty: int, oid: int, ts: int = 1) -> OrderMessage:
    return OrderMessage(MSG_LIMIT, SIDE_BID, qty, price, oid, 1, ts, 0)


def _limit_ask(price: int, qty: int, oid: int, ts: int = 1) -> OrderMessage:
    return OrderMessage(MSG_LIMIT, SIDE_ASK, qty, price, oid, 1, ts, 0)


def _market_buy(qty: int, oid: int, ts: int = 2) -> OrderMessage:
    return OrderMessage(MSG_MARKET, SIDE_BID, qty, 0, oid, 1, ts, 0)


def _market_sell(qty: int, oid: int, ts: int = 2) -> OrderMessage:
    return OrderMessage(MSG_MARKET, SIDE_ASK, qty, 0, oid, 1, ts, 0)


def _cancel_bid(price: int, qty: int, oid: int, ts: int = 3) -> OrderMessage:
    return OrderMessage(MSG_CANCEL, SIDE_BID, qty, price, oid, 1, ts, 0)


class TestBookStateCreation:
    def test_empty_state(self) -> None:
        state = make_book_state()
        assert state.asks == []
        assert state.bids == []
        assert state.trades == []

    def test_best_bid_ask_empty(self) -> None:
        state = make_book_state()
        assert get_best_bid(state) is None
        assert get_best_ask(state) is None


class TestLimitOrders:
    def test_bid_rests(self) -> None:
        state = make_book_state()
        process_message(state, _limit_bid(100, 10, 1))
        assert get_best_bid(state) == 100
        assert get_best_ask(state) is None

    def test_ask_rests(self) -> None:
        state = make_book_state()
        process_message(state, _limit_ask(105, 5, 1))
        assert get_best_ask(state) == 105

    def test_multiple_bids_best_is_highest(self) -> None:
        state = make_book_state()
        process_message(state, _limit_bid(98, 5, 1, ts=1))
        process_message(state, _limit_bid(100, 5, 2, ts=2))
        process_message(state, _limit_bid(99, 5, 3, ts=3))
        assert get_best_bid(state) == 100

    def test_crossing_limit_generates_fill(self) -> None:
        state = make_book_state()
        process_message(state, _limit_ask(100, 5, 1))
        process_message(state, _limit_bid(101, 3, 2))
        assert len(state.trades) == 1
        assert state.trades[0].price == 100
        assert state.trades[0].quantity == 3


class TestMarketOrders:
    def test_market_buy_fills_against_asks(self) -> None:
        state = make_book_state()
        process_message(state, _limit_ask(100, 10, 1))
        process_message(state, _market_buy(5, 2))
        assert len(state.trades) == 1
        assert state.trades[0].quantity == 5
        assert state.trades[0].price == 100
        # 5 units remain
        assert get_best_ask(state) == 100

    def test_market_sell_fills_against_bids(self) -> None:
        state = make_book_state()
        process_message(state, _limit_bid(99, 10, 1))
        process_message(state, _market_sell(4, 2))
        assert len(state.trades) == 1
        assert state.trades[0].quantity == 4
        assert state.trades[0].price == 99

    def test_market_walks_levels(self) -> None:
        state = make_book_state()
        process_message(state, _limit_ask(100, 3, 1, ts=1))
        process_message(state, _limit_ask(101, 5, 2, ts=2))
        process_message(state, _market_buy(6, 3))
        assert len(state.trades) == 2
        assert state.trades[0].quantity == 3
        assert state.trades[0].price == 100
        assert state.trades[1].quantity == 3
        assert state.trades[1].price == 101


class TestCancelOrder:
    def test_cancel_removes_order(self) -> None:
        state = make_book_state()
        process_message(state, _limit_bid(100, 5, 1))
        process_message(state, _cancel_bid(100, 5, 1))
        assert get_best_bid(state) is None

    def test_cancel_reduces_quantity(self) -> None:
        state = make_book_state()
        process_message(state, _limit_bid(100, 10, 1))
        process_message(state, _cancel_bid(100, 3, 1))
        assert get_best_bid(state) == 100
        assert state.bids[0][1] == 7


class TestPriceTimePriority:
    def test_fifo_at_same_price(self) -> None:
        """Earlier order matched first at same price (JAX-LOB time priority)."""
        state = make_book_state()
        process_message(state, _limit_ask(100, 5, 1, ts=10))
        process_message(state, _limit_ask(100, 5, 2, ts=20))
        process_message(state, _market_buy(3, 3, ts=30))
        assert state.trades[0].resting_order_id == 1  # earlier ts matched first


class TestBatchProcessing:
    def test_batch_produces_same_as_sequential(self) -> None:
        msgs = [
            _limit_bid(99, 10, 1, ts=1),
            _limit_ask(101, 10, 2, ts=2),
            _market_buy(5, 3, ts=3),
            _market_sell(3, 4, ts=4),
        ]
        # Sequential
        state1 = make_book_state()
        for m in msgs:
            process_message(state1, m)
        # Batch
        state2 = make_book_state()
        process_message_batch(state2, msgs)
        assert compute_state_digest(state1) == compute_state_digest(state2)


class TestParallelBooks:
    def test_parallel_execution(self) -> None:
        msgs_book1 = [_limit_bid(100, 10, 1), _limit_ask(102, 5, 2)]
        msgs_book2 = [_limit_bid(50, 20, 1), _market_sell(5, 2, ts=2)]
        result = run_parallel_books(2, [msgs_book1, msgs_book2])
        assert len(result.final_states) == 2
        assert len(result.digests) == 2
        assert result.digests[0] != result.digests[1]

    def test_wrong_n_books_raises(self) -> None:
        with pytest.raises(JaxLobSimError):
            run_parallel_books(3, [[_limit_bid(100, 10, 1)], [_limit_bid(50, 10, 2)]])


class TestL2Snapshot:
    def test_snapshot_aggregates_levels(self) -> None:
        state = make_book_state()
        process_message(state, _limit_bid(99, 5, 1))
        process_message(state, _limit_bid(99, 3, 2, ts=2))
        process_message(state, _limit_bid(98, 7, 3, ts=3))
        process_message(state, _limit_ask(101, 4, 4))
        snap = get_l2_snapshot(state, n_levels=5)
        assert snap.best_bid == 99
        assert snap.best_ask == 101
        assert snap.bid_levels[0] == (99, 8)  # aggregated
        assert snap.spread == 2


class TestReplayDeterminism:
    def test_three_runs_identical_digest(self) -> None:
        msgs = [
            _limit_bid(99, 10, 1, ts=1),
            _limit_ask(101, 8, 2, ts=2),
            _limit_bid(100, 5, 3, ts=3),
            _market_buy(6, 4, ts=4),
            _cancel_bid(99, 3, 1, ts=5),
        ]
        digests = []
        for _ in range(3):
            state = make_book_state()
            process_message_batch(state, msgs)
            digests.append(compute_state_digest(state))
        assert digests[0] == digests[1] == digests[2]
