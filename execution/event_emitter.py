"""EXEC-04 / HAZ-04 — event router across bus lanes.

Routes a pre-constructed Event onto the correct lane. Never constructs
typed events (B27/B28/INV-71) — that is the responsibility of each
engine's internal domain.

B1:       No imports from engine tiers.
B27/B28:  Never constructs SignalEvent, ExecutionEvent, SystemEvent, HazardEvent.
INV-15:   Routing is a pure function of event.kind.
"""

from __future__ import annotations

from core.contracts.events import Event, EventKind, ExecutionEvent, HazardEvent, SignalEvent, SystemEvent
from execution.async_bus import AsyncBus, get_async_bus
from execution.fast_lane import FastLane, get_fast_lane
from execution.hazard_lane import HazardLane, get_hazard_lane
from execution.offline_lane import OfflineLane, get_offline_lane

__all__ = ["EventEmitter", "get_event_emitter"]


class EventEmitter:
    """Routes events to the appropriate lane.

    - SIGNAL + EXECUTION → fast_lane (synchronous hot path) + async_bus
    - HAZARD → hazard_lane (priority) + async_bus
    - SYSTEM → offline_lane (buffered) + async_bus

    The async_bus always receives a copy for any subscribers that want
    all event kinds in one subscription point (e.g. audit sinks).
    """

    def __init__(
        self,
        *,
        fast_lane: FastLane | None = None,
        hazard_lane: HazardLane | None = None,
        offline_lane: OfflineLane | None = None,
        async_bus: AsyncBus | None = None,
    ) -> None:
        self._fast = fast_lane or get_fast_lane()
        self._hazard = hazard_lane or get_hazard_lane()
        self._offline = offline_lane or get_offline_lane()
        self._bus = async_bus or get_async_bus()

    def emit(self, event: Event) -> None:
        """Route event to its canonical lane(s)."""
        kind = event.kind
        if kind is EventKind.SIGNAL:
            self._fast.emit(event)  # type: ignore[arg-type]
        elif kind is EventKind.EXECUTION:
            self._fast.emit(event)  # type: ignore[arg-type]
        elif kind is EventKind.HAZARD:
            self._hazard.emit(event)  # type: ignore[arg-type]
        elif kind is EventKind.SYSTEM:
            self._offline.emit(event)  # type: ignore[arg-type]
        # All events also flow onto the single async bus for audit sinks.
        self._bus.emit(event)


_emitter: EventEmitter | None = None


def get_event_emitter() -> EventEmitter:
    """Return the process-wide :class:`EventEmitter` singleton."""
    global _emitter
    if _emitter is None:
        _emitter = EventEmitter()
    return _emitter
