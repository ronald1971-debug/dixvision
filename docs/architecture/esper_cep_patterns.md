# C-95 — Esper CEP: Complex Event Processing Patterns

> ADAPTED FROM: EsperTech/esper (GPL-2.0) — pattern reference only
> Source: EPL language docs, temporal event patterns, sliding windows

## Temporal Event Patterns for Hazard Detection

Esper's Event Processing Language (EPL) defines temporal patterns that
map to DIX hazard detection scenarios:

### Pattern 1: Temporal Sequence

```epl
-- Alert if price drop > 5% followed by volume spike within 30 seconds
SELECT * FROM pattern [
    every a=PriceEvent(pct_change < -0.05)
    -> b=VolumeEvent(volume > avg_volume * 3) WHERE timer:within(30 sec)
]
```

**DIX equivalent** in `sensor_array.py`:
```python
# Temporal window: price_drop then volume_spike within 30s
if price_drop_event and volume_spike_within(30):
    emit_hazard(HazardLevel.WARNING, "price-volume divergence")
```

### Pattern 2: Sliding Window Aggregation

```epl
-- Rolling 5-minute VWAP deviation
SELECT symbol, avg(price) as vwap_5m
FROM TradeEvent#time(5 min)
GROUP BY symbol
HAVING abs(price - avg(price)) / avg(price) > 0.02
```

### Pattern 3: Absence Detection

```epl
-- Alert if no heartbeat from exchange within 10 seconds
SELECT * FROM pattern [
    every HeartbeatEvent -> (timer:interval(10 sec) AND NOT HeartbeatEvent)
]
```

## Multi-Signal Causality Chains

```epl
-- Three correlated signals within 60 seconds = regime change
SELECT * FROM pattern [
    every (a=VolatilitySpike -> b=CorrelationBreak -> c=LiquidityDrop)
    WHERE timer:within(60 sec)
]
```

## Enhancement Spec for sensor_array.py

The hazard sensor array should implement:

1. **Temporal window buffers**: Ring buffer of recent events per sensor type.
2. **Pattern matchers**: State machines that track multi-event sequences.
3. **Absence timers**: Detect missing heartbeats/data gaps.
4. **Window aggregations**: Rolling stats (mean, std) over configurable windows.

### Proposed API

```python
class TemporalPattern:
    def __init__(self, events: list[str], window_seconds: float): ...
    def match(self, event: HazardEvent) -> bool: ...

class SensorArray:
    def add_temporal_pattern(self, pattern: TemporalPattern, action: Callable): ...
    def add_absence_detector(self, event_type: str, timeout_s: float): ...
    def add_window_aggregation(self, event_type: str, window_s: float): ...
```
