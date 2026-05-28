# I-33 — LOB Implementation Decision

**ADAPTED FROM:** https://github.com/Kautenja/limit-order-book  
**License:** MIT

## Summary

This document records the performance comparison between the current
Python `sortedcontainers`-based LOB and the C++ reference implementation
from Kautenja/limit-order-book.

## Current Implementation

`execution_engine/market_data/orderbook.py` uses `sortedcontainers.SortedList`
for price level management with O(log n) insert/remove operations.

## C++ Reference (Kautenja)

The C++ implementation uses:
- **SortedList** price level management (red-black tree)
- **FIFO queue** per price level for time priority
- **Zero-allocation matching** via pre-allocated node pool

### Performance Characteristics

| Metric | Python (sortedcontainers) | C++ (Kautenja) |
|--------|--------------------------|----------------|
| Add order | O(log n) | O(log n) |
| Cancel order | O(log n) | O(1) amortized |
| Match (top-of-book) | O(1) | O(1) |
| Memory per order | ~200 bytes (Python object) | ~48 bytes (C struct) |

## Decision Criteria

If C++ LOB provides **>50% latency improvement** in the orderbook hot path:
→ Use as architecture reference for **PyO3 Rust rewrite** (I-38)

If improvement is <50%:
→ Keep Python sortedcontainers implementation (simpler maintenance)

## Benchmark Results

Run `pytest tests/bench/test_lob_performance_bench.py -v` to generate
current numbers on your hardware.

## Recommendation

For DIX's use case (institutional-grade, sub-millisecond requirements):
1. **Phase 1** (current): Python sortedcontainers — sufficient for <10K active orders
2. **Phase 2** (if needed): Rust LOB via PyO3 (I-38) — informed by C++ patterns
3. The Kautenja C++ design (FIFO per level, pre-allocated nodes) should guide
   the Rust implementation if Phase 2 is triggered by latency requirements.
