# ADAPTED FROM: Kautenja/limit-order-book
# (src/limit_order_book.hpp — SortedList price level management, FIFO queue;
#  benchmark comparison: C++ LOB vs Python sortedcontainers LOB)
"""I-33 — LOB performance benchmark: C++ reference vs Python sortedcontainers.

This benchmark measures:
    1. Python sortedcontainers LOB (current implementation)
    2. C++ LOB (Kautenja) via Python bindings if available

Decision criteria: If C++ LOB gives >50% latency improvement in the
orderbook hot path, use as reference for PyO3 Rust rewrite design.

Results feed into ``docs/lob_implementation_decision.md``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BenchResult:
    """Result of a single benchmark run."""

    name: str
    ops_per_second: float
    total_ops: int
    elapsed_seconds: float


def bench_python_sortedcontainers_lob(n_ops: int = 10_000) -> BenchResult:
    """Benchmark Python sortedcontainers-based LOB.

    Simulates add/cancel/match operations on a pure-Python LOB
    using sortedcontainers.SortedList for price levels.
    """
    try:
        from sortedcontainers import SortedList
    except ImportError:
        return BenchResult(
            name="python_sortedcontainers",
            ops_per_second=0.0,
            total_ops=0,
            elapsed_seconds=0.0,
        )

    bids: SortedList[tuple[float, int, int]] = SortedList()
    asks: SortedList[tuple[float, int, int]] = SortedList()

    start = time.perf_counter()
    for i in range(n_ops):
        price = 100.0 + (i % 100) * 0.01
        qty = 10 + (i % 50)
        if i % 2 == 0:
            bids.add((-price, i, qty))  # negative for descending
        else:
            asks.add((price, i, qty))

        # Simulate matching
        if bids and asks:
            best_bid_price = -bids[0][0]
            best_ask_price = asks[0][0]
            if best_bid_price >= best_ask_price:
                bids.pop(0)
                asks.pop(0)

    elapsed = time.perf_counter() - start
    return BenchResult(
        name="python_sortedcontainers",
        ops_per_second=n_ops / elapsed if elapsed > 0 else 0,
        total_ops=n_ops,
        elapsed_seconds=elapsed,
    )


def bench_cpp_lob(n_ops: int = 10_000) -> BenchResult | None:
    """Benchmark C++ LOB (Kautenja) if Python bindings available.

    Returns None if the C++ library is not installed.
    """
    try:
        import limit_order_book  # noqa: F401  # Kautenja bindings

        start = time.perf_counter()
        book = limit_order_book.LimitOrderBook()
        for i in range(n_ops):
            price = 10000 + (i % 100)
            qty = 10 + (i % 50)
            if i % 2 == 0:
                book.limit(True, i, qty, price)  # buy
            else:
                book.limit(False, i, qty, price)  # sell
        elapsed = time.perf_counter() - start
        return BenchResult(
            name="cpp_kautenja",
            ops_per_second=n_ops / elapsed if elapsed > 0 else 0,
            total_ops=n_ops,
            elapsed_seconds=elapsed,
        )
    except ImportError:
        return None


def test_python_lob_benchmark():
    """Run Python LOB benchmark and verify it completes."""
    result = bench_python_sortedcontainers_lob(n_ops=1_000)
    assert result.ops_per_second > 0
    assert result.total_ops == 1_000
    assert result.elapsed_seconds > 0


def test_cpp_lob_benchmark_or_skip():
    """Run C++ LOB benchmark if available, skip otherwise."""
    result = bench_cpp_lob(n_ops=1_000)
    if result is None:
        # C++ bindings not installed — expected in CI
        return
    assert result.ops_per_second > 0


def test_benchmark_comparison():
    """Compare Python vs C++ LOB performance."""
    py_result = bench_python_sortedcontainers_lob(n_ops=5_000)
    cpp_result = bench_cpp_lob(n_ops=5_000)

    # Python benchmark must always work
    assert py_result.ops_per_second > 0

    if cpp_result is not None:
        speedup = cpp_result.ops_per_second / py_result.ops_per_second
        # Document the speedup for decision-making
        assert speedup > 0  # At minimum it runs
