# C-96 — AAT (AsyncAlgoTrading): Async Adapter Architecture

> ADAPTED FROM: AsyncAlgoTrading/aat (BSD-3-Clause)
> Source: `aat/core/engine.py`, `aat/exchange/`, `aat/strategy/`

## Async Engine Patterns

AAT's engine uses Python asyncio throughout:

```python
class TradingEngine:
    async def start(self):
        await asyncio.gather(
            self._process_market_data(),
            self._process_orders(),
            self._process_risk(),
        )
```

Key insight: **concurrent feed handling** via `asyncio.gather()` allows
multiple exchange WebSocket feeds to run in parallel without threading.

## Async Exchange Adapters

AAT's exchange adapter pattern:

```python
class Exchange(ABC):
    async def connect(self) -> None: ...
    async def subscribe(self, instruments: list) -> None: ...
    async def place_order(self, order: Order) -> OrderResult: ...
    async def cancel_order(self, order_id: str) -> bool: ...

    # Data feed — yields events as they arrive
    async def market_data_stream(self) -> AsyncIterator[MarketData]: ...
```

## Strategy Lifecycle

```python
class Strategy(ABC):
    async def on_start(self) -> None: ...
    async def on_data(self, data: MarketData) -> None: ...
    async def on_order(self, order: Order) -> None: ...
    async def on_fill(self, fill: Fill) -> None: ...
    async def on_stop(self) -> None: ...
```

## Adapter Concurrency Patterns for DIX

### Pattern 1: Multi-Exchange Fan-In

```python
async def multi_exchange_feed(adapters: list[BrokerAdapter]):
    streams = [adapter.stream() for adapter in adapters]
    async for event in merge_streams(streams):
        await event_fabric.publish(event)
```

### Pattern 2: Order Lifecycle Async State Machine

```python
async def manage_order(adapter, order):
    result = await adapter.place_order(order)
    while result.status == "PENDING":
        result = await adapter.check_order(result.order_id)
        await asyncio.sleep(0.1)
    return result
```

### Pattern 3: Graceful Shutdown

```python
async def shutdown(adapters):
    # Cancel all pending orders first
    tasks = [adapter.cancel_all() for adapter in adapters]
    await asyncio.gather(*tasks, return_exceptions=True)
    # Then disconnect
    for adapter in adapters:
        await adapter.disconnect()
```

## Applicability to DIX

| AAT Pattern | DIX Integration Point |
|-------------|----------------------|
| Async engine | `execution_engine/` main loop |
| Multi-feed | `execution_engine/adapters/` WebSocket feeds |
| Strategy lifecycle | `intelligence_engine/` signal generation |
| Graceful shutdown | `immutable_core/kill_switch.py` |

## Recommendations

1. DIX execution adapters should expose `async` interfaces.
2. Use `asyncio.TaskGroup` (Python 3.11+) for structured concurrency.
3. Implement cancellation via `asyncio.CancelledError` propagation.
4. WebSocket feeds should auto-reconnect with exponential backoff.
