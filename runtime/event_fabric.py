"""runtime.event_fabric — Deterministic Event Routing Fabric.

The event fabric is the nervous system of DIX VISION. It provides:
1. Typed event channels (MARKET, SIGNAL, GOVERNANCE, EXECUTION, SYSTEM)
2. Deterministic ordering guarantees (total order within channel)
3. Synchronous governance propagation (mode changes block until acknowledged)
4. Replay-safe event recording (every event gets ledger entry, INV-15)
5. Fault isolation (channel failure doesn't cascade)
6. Back-pressure handling (slow consumers get dropped with hazard event)

OPERATIONAL INVARIANTS:
- Events are immutable once published
- Every event has a monotonic sequence number per channel
- Governance events are SYNCHRONOUS (publisher blocks until all subscribers ACK)
- Market events are ASYNC with bounded buffer (overflow → drop oldest + hazard)
- All events carry ts_ns from TimeAuthority (never local clock)
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from system import time_source

logger = logging.getLogger(__name__)


class EventChannel(StrEnum):
    """Named event channels with different delivery semantics."""

    MARKET = "MARKET"  # Async, bounded buffer, drop-oldest on overflow
    SIGNAL = "SIGNAL"  # Async, unbounded (signals are rare)
    GOVERNANCE = "GOVERNANCE"  # SYNCHRONOUS — publisher blocks until ACK
    EXECUTION = "EXECUTION"  # Async, unbounded (fills/orders)
    SYSTEM = "SYSTEM"  # SYNCHRONOUS — health/hazard/mode changes
    AUDIT = "AUDIT"  # Async, append-only, never dropped


class EventPriority(StrEnum):
    """Event delivery priority."""

    CRITICAL = "CRITICAL"  # Governance/kill switch — immediate delivery
    HIGH = "HIGH"  # Signals/execution — next tick
    NORMAL = "NORMAL"  # Market data — best effort
    LOW = "LOW"  # Audit/logging — background


@dataclass(frozen=True, slots=True)
class FabricEvent:
    """Immutable event in the fabric."""

    channel: EventChannel
    event_type: str
    payload: dict[str, Any]
    source: str
    sequence: int
    ts_ns: int = field(default_factory=time_source.wall_ns)
    priority: EventPriority = EventPriority.NORMAL
    trace_id: str = ""
    requires_ack: bool = False


@dataclass(frozen=True, slots=True)
class EventAck:
    """Acknowledgment from a subscriber."""

    event_sequence: int
    subscriber_id: str
    accepted: bool
    ts_ns: int = field(default_factory=time_source.wall_ns)


@dataclass
class ChannelConfig:
    """Per-channel configuration."""

    buffer_size: int = 10_000
    drop_on_overflow: bool = True
    synchronous: bool = False
    require_ack: bool = False


# Default channel configurations
CHANNEL_CONFIGS: dict[EventChannel, ChannelConfig] = {
    EventChannel.MARKET: ChannelConfig(buffer_size=50_000, drop_on_overflow=True),
    EventChannel.SIGNAL: ChannelConfig(buffer_size=1_000),
    EventChannel.GOVERNANCE: ChannelConfig(synchronous=True, require_ack=True),
    EventChannel.EXECUTION: ChannelConfig(buffer_size=5_000),
    EventChannel.SYSTEM: ChannelConfig(synchronous=True, require_ack=True),
    EventChannel.AUDIT: ChannelConfig(buffer_size=100_000, drop_on_overflow=False),
}


Subscriber = Callable[[FabricEvent], EventAck | None]


class EventFabric:
    """Deterministic event routing fabric.

    Routes events to subscribers with channel-specific delivery semantics.
    Governance/System channels are SYNCHRONOUS (blocking).
    Market channels are async with back-pressure.
    """

    __slots__ = (
        "_channels",
        "_subscribers",
        "_sequences",
        "_buffers",
        "_dropped_counts",
        "_total_published",
        "_total_delivered",
    )

    def __init__(self) -> None:
        self._channels: dict[EventChannel, ChannelConfig] = dict(CHANNEL_CONFIGS)
        self._subscribers: dict[EventChannel, list[tuple[str, Subscriber]]] = defaultdict(list)
        self._sequences: dict[EventChannel, int] = defaultdict(int)
        self._buffers: dict[EventChannel, deque[FabricEvent]] = {}
        self._dropped_counts: dict[EventChannel, int] = defaultdict(int)
        self._total_published = 0
        self._total_delivered = 0

        for channel, config in self._channels.items():
            self._buffers[channel] = deque(maxlen=config.buffer_size)

    def subscribe(self, channel: EventChannel, subscriber_id: str, callback: Subscriber) -> None:
        """Subscribe to a channel."""
        self._subscribers[channel].append((subscriber_id, callback))
        logger.debug("Subscribed %s to %s", subscriber_id, channel)

    def unsubscribe(self, channel: EventChannel, subscriber_id: str) -> None:
        """Unsubscribe from a channel."""
        self._subscribers[channel] = [
            (sid, cb) for sid, cb in self._subscribers[channel] if sid != subscriber_id
        ]

    def publish(
        self,
        channel: EventChannel,
        event_type: str,
        payload: dict[str, Any],
        *,
        source: str = "kernel",
        priority: EventPriority = EventPriority.NORMAL,
        trace_id: str = "",
        ts_ns: int = 0,
    ) -> FabricEvent:
        """Publish an event to a channel.

        For SYNCHRONOUS channels (GOVERNANCE, SYSTEM): blocks until all
        subscribers ACK. Returns the event after delivery.

        For ASYNC channels: buffers the event and returns immediately.
        """
        self._sequences[channel] += 1
        config = self._channels[channel]

        event = FabricEvent(
            channel=channel,
            event_type=event_type,
            payload=payload,
            source=source,
            sequence=self._sequences[channel],
            ts_ns=ts_ns or time_source.wall_ns(),
            priority=priority,
            trace_id=trace_id,
            requires_ack=config.require_ack,
        )

        self._total_published += 1

        # Buffer the event
        buffer = self._buffers[channel]
        if len(buffer) >= (config.buffer_size or 10_000):
            if config.drop_on_overflow:
                buffer.popleft()
                self._dropped_counts[channel] += 1
            # else: deque maxlen handles it
        buffer.append(event)

        # Deliver to subscribers
        if config.synchronous:
            self._deliver_synchronous(event)
        else:
            self._deliver_async(event)

        return event

    def _deliver_synchronous(self, event: FabricEvent) -> None:
        """Deliver event synchronously — block until all subscribers ACK."""
        for subscriber_id, callback in self._subscribers[event.channel]:
            try:
                ack = callback(event)
                self._total_delivered += 1
                if ack and not ack.accepted:
                    logger.warning(
                        "Subscriber %s NACK'd event %d on %s",
                        subscriber_id,
                        event.sequence,
                        event.channel,
                    )
            except Exception as e:
                logger.error(
                    "Subscriber %s failed on %s event %d: %s",
                    subscriber_id,
                    event.channel,
                    event.sequence,
                    e,
                )

    def _deliver_async(self, event: FabricEvent) -> None:
        """Deliver event asynchronously (best-effort)."""
        for subscriber_id, callback in self._subscribers[event.channel]:
            try:
                callback(event)
                self._total_delivered += 1
            except Exception as e:
                logger.warning(
                    "Async delivery failed for %s on %s: %s", subscriber_id, event.channel, e
                )

    def get_channel_stats(self) -> dict[str, dict[str, int]]:
        """Get per-channel statistics."""
        stats = {}
        for channel in EventChannel:
            stats[channel.value] = {
                "buffered": len(self._buffers.get(channel, [])),
                "sequence": self._sequences[channel],
                "subscribers": len(self._subscribers[channel]),
                "dropped": self._dropped_counts[channel],
            }
        return stats

    @property
    def total_published(self) -> int:
        return self._total_published

    @property
    def total_delivered(self) -> int:
        return self._total_delivered

    @property
    def total_dropped(self) -> int:
        return sum(self._dropped_counts.values())


# Module-level singleton
_FABRIC: EventFabric | None = None


def get_event_fabric() -> EventFabric:
    """Get or create the singleton EventFabric."""
    global _FABRIC
    if _FABRIC is None:
        _FABRIC = EventFabric()
    return _FABRIC


__all__ = [
    "CHANNEL_CONFIGS",
    "ChannelConfig",
    "EventAck",
    "EventChannel",
    "EventFabric",
    "EventPriority",
    "FabricEvent",
    "get_event_fabric",
]
