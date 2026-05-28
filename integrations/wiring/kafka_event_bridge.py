"""Bridge: Kafka adapter → system_engine/streaming.

Wires the Kafka OSS adapter into the event fabric as an alternative
transport for distributed deployments. Works alongside existing
event_fabric (bytewax), faust_bus, and kafka_bus modules.

The bridge provides:
- Market event publishing (ticks, OHLCV, order book updates)
- Signal routing (from intelligence_engine to execution_engine)
- Governance event broadcasting (decisions, mode changes, hazards)
- Telemetry streaming (metrics, traces, audit log entries)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from integrations.kafka_adapter.streaming import (
    KafkaStreamingAdapter,
    Topic,
)


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """An event routed through the Kafka bridge."""

    event_id: str
    event_type: str
    source: str
    payload: dict[str, Any]
    topic: str
    ts_ns: int


class KafkaEventBridge:
    """Bridge between Kafka adapter and system_engine/streaming.

    Provides:
    - Publish market data events to the event fabric
    - Publish trading signals for execution routing
    - Publish governance decisions and hazard alerts
    - Subscribe to event streams for processing
    - Event replay from topic offsets

    Compatible with existing streaming modules:
    - system_engine/streaming/event_fabric.py (bytewax)
    - system_engine/streaming/kafka_bus.py (aiokafka)
    """

    def __init__(self) -> None:
        self._adapter = KafkaStreamingAdapter()
        self._connected = False
        self._published_count = 0
        self._consumed_count = 0
        self._event_log: list[EventEnvelope] = []

    def initialize(self) -> bool:
        """Connect to Kafka and set up topics."""
        result = self._adapter.connect()
        self._connected = result
        return result

    # --- Publish Events ---

    def publish_market_tick(
        self,
        symbol: str,
        *,
        price: float,
        volume: float = 0.0,
        bid: float = 0.0,
        ask: float = 0.0,
    ) -> EventEnvelope:
        """Publish a market tick event."""
        topic = self._symbol_to_topic(symbol)
        payload = {
            "symbol": symbol,
            "price": price,
            "volume": volume,
            "bid": bid,
            "ask": ask,
        }
        msg = self._adapter.publish_market_event(
            symbol=symbol,
            event_type="tick",
            data={"price": price, "volume": volume, "bid": bid, "ask": ask},
        )
        return self._envelope(
            event_type="market.tick",
            source="sensory",
            payload=payload,
            topic=topic.value if isinstance(topic, Topic) else str(topic),
            ts_ns=msg.ts_ns,
        )

    def publish_signal(
        self,
        *,
        signal_id: str,
        symbol: str,
        direction: str,
        confidence: float,
        source_engine: str = "intelligence_engine",
    ) -> EventEnvelope:
        """Publish a trading signal for execution routing."""
        payload = {
            "signal_id": signal_id,
            "symbol": symbol,
            "direction": direction,
            "confidence": confidence,
            "source": source_engine,
        }
        msg = self._adapter.publish_signal(
            signal_id=signal_id,
            symbol=symbol,
            side=direction,
            confidence=confidence,
        )
        return self._envelope(
            event_type="signal.generated",
            source=source_engine,
            payload=payload,
            topic=Topic.SIGNALS.value,
            ts_ns=msg.ts_ns,
        )

    def publish_governance_event(
        self,
        *,
        decision_type: str,
        decision: str,
        reason: str = "",
        actor: str = "governance_engine",
    ) -> EventEnvelope:
        """Publish a governance decision event."""
        payload = {
            "decision_type": decision_type,
            "decision": decision,
            "reason": reason,
            "actor": actor,
        }
        msg = self._adapter.publish_governance_decision(
            decision_id=f"gov_{self._published_count + 1}",
            action=decision_type,
            result=decision,
        )
        return self._envelope(
            event_type="governance.decision",
            source=actor,
            payload=payload,
            topic=Topic.GOVERNANCE.value,
            ts_ns=msg.ts_ns,
        )

    def publish_execution_event(
        self,
        *,
        order_id: str,
        symbol: str,
        side: str,
        status: str,
        filled: float = 0.0,
        price: float = 0.0,
    ) -> EventEnvelope:
        """Publish an execution lifecycle event."""
        payload = {
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "status": status,
            "filled": filled,
            "price": price,
        }
        msg = self._adapter.publish_execution_event(
            order_id=order_id,
            event_type=status,
            data={"symbol": symbol, "side": side, "filled": filled, "price": price},
        )
        return self._envelope(
            event_type="execution.update",
            source="execution_engine",
            payload=payload,
            topic=Topic.EXECUTION.value,
            ts_ns=msg.ts_ns,
        )

    # --- Subscribe/Consume ---

    def consume_signals(
        self, *, max_messages: int = 10, timeout_ms: int = 1000
    ) -> list[EventEnvelope]:
        """Consume pending trading signals."""
        self._adapter.subscribe([Topic.SIGNALS])
        messages = self._adapter.consume(
            Topic.SIGNALS, max_messages=max_messages, timeout_ms=timeout_ms
        )
        envelopes = [
            self._envelope(
                event_type="signal.received",
                source="kafka",
                payload=m.value,
                topic=Topic.SIGNALS.value,
                ts_ns=m.ts_ns,
            )
            for m in messages
        ]
        self._consumed_count += len(envelopes)
        return envelopes

    def consume_governance(
        self, *, max_messages: int = 10, timeout_ms: int = 1000
    ) -> list[EventEnvelope]:
        """Consume pending governance events."""
        self._adapter.subscribe([Topic.GOVERNANCE])
        messages = self._adapter.consume(
            Topic.GOVERNANCE, max_messages=max_messages, timeout_ms=timeout_ms
        )
        envelopes = [
            self._envelope(
                event_type="governance.received",
                source="kafka",
                payload=m.value,
                topic=Topic.GOVERNANCE.value,
                ts_ns=m.ts_ns,
            )
            for m in messages
        ]
        self._consumed_count += len(envelopes)
        return envelopes

    # --- Metrics ---

    @property
    def published_count(self) -> int:
        """Total events published."""
        return self._published_count

    @property
    def consumed_count(self) -> int:
        """Total events consumed."""
        return self._consumed_count

    @property
    def is_connected(self) -> bool:
        """Whether Kafka is connected."""
        return self._connected

    # --- Internal ---

    def _symbol_to_topic(self, symbol: str) -> Topic:
        """Map a trading symbol to its Kafka topic."""
        sym = symbol.upper().replace("/", "")
        if "BTC" in sym:
            return Topic.MARKET_BTC
        if "ETH" in sym:
            return Topic.MARKET_ETH
        if "SOL" in sym:
            return Topic.MARKET_SOL
        return Topic.MARKET_BTC

    def _envelope(
        self,
        *,
        event_type: str,
        source: str,
        payload: dict[str, Any],
        topic: str,
        ts_ns: int,
    ) -> EventEnvelope:
        """Create an event envelope."""
        self._published_count += 1
        eid = f"evt_{self._published_count:010d}"
        env = EventEnvelope(
            event_id=eid,
            event_type=event_type,
            source=source,
            payload=payload,
            topic=topic,
            ts_ns=ts_ns,
        )
        self._event_log.append(env)
        if len(self._event_log) > 10000:
            self._event_log = self._event_log[-10000:]
        return env
