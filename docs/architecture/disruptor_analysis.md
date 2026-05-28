# C-93 — LMAX Disruptor: Ring Buffer Architecture Analysis

> ADAPTED FROM: LMAX-Exchange/disruptor (Apache-2.0)
> Source: `src/main/java/com/lmax/disruptor/RingBuffer.java`,
> `EventProcessor.java`, `SequenceBarrier.java`

## How Ring Buffers Eliminate Lock Contention

The LMAX Disruptor replaces traditional queues with a pre-allocated ring
buffer where:

1. **Single producer** writes to the next slot via an atomic CAS on the
   sequence counter — no lock acquisition.
2. **Multiple consumers** each maintain their own sequence counter; they
   advance independently without interfering with the producer or each other.
3. **Pre-allocation** means no object creation on the hot path — GC pauses
   are eliminated.

## Sequence Barriers for Dependency Tracking

```
Producer → [RingBuffer] → Consumer A (signal processing)
                       → Consumer B (risk check, depends on A)
                       → Consumer C (execution, depends on B)
```

`SequenceBarrier` lets Consumer B wait until Consumer A has processed
the same sequence, without polling or blocking the producer.

## Application to DIX Per-Tick Event Bus

| DIX Component | Disruptor Mapping |
|---------------|-------------------|
| `system_engine/streaming/event_fabric.py` | RingBuffer (pre-allocated) |
| HazardSensor subscribers | EventProcessors (multi-consumer) |
| Governance gate | SequenceBarrier (dependency) |
| Kill switch | Single highest-priority consumer |

## Python asyncio.Queue Comparison

| Metric | asyncio.Queue | Disruptor Pattern |
|--------|--------------|-------------------|
| Lock contention | mutex per op | CAS only (producer) |
| Object allocation | per-event | zero (pre-allocated) |
| Batching | manual | built-in (batch aware) |
| Multi-consumer | fan-out copy | shared read |
| Latency (p99) | ~50μs | ~0.1μs |

## When Does DIX Need This?

Current throughput: ~10k events/second → asyncio.Queue is fine.
Threshold for Disruptor pattern: >500k events/second sustained.

The Python implementation would use:
- `multiprocessing.shared_memory` for the ring buffer
- `ctypes` atomic operations for sequence counters
- Or: Rust/C extension via PyO3/cffi for the hot path
