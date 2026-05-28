# C-92 — Barter-RS: Rust Hot Path Reference Architecture

> ADAPTED FROM: barter-rs/barter-rs (MIT)
> Source: `barter/src/engine/`, `barter/src/portfolio/`, `barter/src/execution/`

## Zero-Copy Event Types (PyO3 Migration)

Barter-RS defines event types as Rust enums with `#[repr(C)]` alignment,
enabling zero-copy serialization between the event bus and consumers.

Key patterns for DIX hot_path rewrite:

1. **Enum-based events**: `MarketEvent`, `SignalEvent`, `OrderEvent` — each
   variant carries its payload inline (no heap allocation).
2. **Arena allocation**: Events allocated from a pre-sized arena, recycled
   after processing (no GC pressure).
3. **Sequence numbering**: Every event carries a monotonic sequence ID for
   replay determinism (maps to INV-15).

## Lock-Free Order Book

Barter's order book uses:
- **Sorted arrays** (not trees) for price levels — cache-friendly iteration.
- **Atomic sequence counters** for detecting stale reads.
- **Single-writer** model: only the matching engine writes; readers observe
  via atomic snapshot.

## Hot Path Rewrite Roadmap

| Phase | Scope | DIX Module | Latency Target |
|-------|-------|-----------|---------------|
| 1 | Event serialization | `execution_engine/hot_path/events.pyi` | <1μs encode |
| 2 | Order book core | `execution_engine/hot_path/book.pyi` | <5μs update |
| 3 | Matching engine | `execution_engine/hot_path/matcher.pyi` | <10μs per order |
| 4 | Full tick-to-trade | all above + network | <50μs total |

## PyO3 Integration Points

```
# Python calls Rust via PyO3:
from dix_hot_path import OrderBook, encode_event

book = OrderBook()           # Rust struct, zero-copy
book.apply(encode_event(e))  # Rust-side processing
```

## Applicability to DIX

- Phase 1 lands when Python tick-to-trade exceeds 1ms (current: ~5ms).
- Phase 2 for market-making strategies requiring sub-100μs book updates.
- Full rewrite justified at >100k messages/second throughput.
