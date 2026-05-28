# C-94 — Aeron: Ultra-Low-Latency Messaging Analysis

> ADAPTED FROM: real-logic/aeron (Apache-2.0)
> Source: `aeron-driver/src/main/java/io/aeron/driver/`,
> `aeron-client/` publication/subscription patterns

## IPC Transport Zero-Copy

Aeron's IPC (Inter-Process Communication) transport:

1. **Memory-mapped files** as the message buffer — no kernel copy on
   publish or receive.
2. **Log buffers** split into terms: producer appends to active term,
   consumers read from completed terms.
3. **No serialization** on the IPC path — messages are written directly
   as bytes into shared memory.

## Exclusive Publications Without Contention

- **Exclusive publication**: single writer per stream, no CAS needed.
- **Concurrent publication**: multiple writers, uses CAS for claim.
- DIX should use exclusive publications (one engine per stream).

## Archive Replay

Aeron Archive records all messages to disk and replays on demand:
- Maps directly to INV-15 (deterministic replay).
- Replay from any sequence position.
- Bounded retention with configurable TTL.

## Applicability to DIX

| Aeron Feature | DIX Equivalent | Current Implementation |
|---------------|---------------|----------------------|
| IPC transport | event_fabric | asyncio.Queue (single process) |
| Archive | state/ledger | SQLite event_store |
| Multi-destination | fan-out | event_fabric subscribers |
| Flow control | backpressure | HazardThrottle |

## When to Adopt

| Scale | Recommendation |
|-------|---------------|
| <10k msg/s | Current asyncio is sufficient |
| 10k–100k msg/s | Consider shared-memory ring buffer |
| >100k msg/s | Aeron IPC justified (via Java/C driver + Python client) |
| >1M msg/s | Aeron + Rust hot path mandatory |

## Integration Path

1. Aeron C driver runs as sidecar process.
2. Python client uses `ctypes` or `cffi` to attach to shared memory.
3. Event fabric becomes a thin wrapper over Aeron publication/subscription.
4. Archive replaces SQLite ledger for hot-tier replay.
