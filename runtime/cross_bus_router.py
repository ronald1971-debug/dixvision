"""runtime.cross_bus_router — Event Bridge: Cognitive Bus ↔ Execution Fabric.

Bridges two separate pub/sub systems:

  state.event_bus   (CognitiveChannel)  — cognitive domain pub/sub
  runtime.event_fabric (EventChannel)   — execution domain routing fabric

Routes FROM cognitive bus TO execution fabric:
  DYON_VIOLATION    → EventChannel.SYSTEM      (hazard/architecture alert)
  DYON_PROPOSAL     → EventChannel.GOVERNANCE  (proposed architecture change)
  INDIRA_INSIGHT    → EventChannel.SIGNAL      (market intelligence signal)
  RISK_BREACH       → EventChannel.SYSTEM      (risk kill-switch alert)

Routes FROM execution fabric TO cognitive bus:
  EventChannel.GOVERNANCE / "MODE_TRANSITION" → CognitiveChannel.INDIRA_THOUGHT
    (so INDIRA knows the system mode changed — affects strategy confidence)

This is the nervous system connection that makes cognitive and execution
subsystems aware of each other without direct coupling.

Authority: runtime tier — imports state.*, runtime.*. Never execution_engine.
INV-15: ts_ns is sourced from event payloads (publisher-supplied).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

_logger = logging.getLogger(__name__)


class CrossBusRouter:
    """Bridges the cognitive event bus and the execution event fabric."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._routed_counts: dict[str, int] = {}

    def activate(self) -> None:
        """Subscribe to both buses and wire the cross-routing.  Idempotent."""
        with self._lock:
            if self._active:
                return
            self._active = True

        self._subscribe_cognitive_to_fabric()
        self._subscribe_fabric_to_cognitive()
        _logger.info("CrossBusRouter: activated (bidirectional bridge live)")

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active": self._active,
                "routed_counts": dict(self._routed_counts),
                "total_routed": sum(self._routed_counts.values()),
            }

    # ------------------------------------------------------------------
    # Cognitive → Fabric
    # ------------------------------------------------------------------

    def _subscribe_cognitive_to_fabric(self) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            bus = get_event_bus()

            bus.subscribe(CognitiveChannel.DYON_VIOLATION,
                          lambda p: self._cog_to_fabric("SYSTEM", "DYON_VIOLATION", p))
            bus.subscribe(CognitiveChannel.DYON_PROPOSAL,
                          lambda p: self._cog_to_fabric("GOVERNANCE", "DYON_PROPOSAL", p))
            bus.subscribe(CognitiveChannel.INDIRA_INSIGHT,
                          lambda p: self._cog_to_fabric("SIGNAL", "INDIRA_INSIGHT", p))
            bus.subscribe(CognitiveChannel.RISK_BREACH,
                          lambda p: self._cog_to_fabric("SYSTEM", "RISK_BREACH", p))
        except Exception as exc:
            _logger.debug("CrossBusRouter._subscribe_cognitive_to_fabric error: %s", exc)

    def _cog_to_fabric(self, channel_name: str, event_type: str, payload: dict[str, Any]) -> None:
        try:
            from runtime.event_fabric import EventChannel, get_event_fabric
            ch = EventChannel(channel_name)
            get_event_fabric().publish(ch, event_type, payload, source="cross_bus_router")
            self._increment(f"cog→fabric:{event_type}")
        except Exception as exc:
            _logger.debug("CrossBusRouter._cog_to_fabric(%s) error: %s", event_type, exc)

    # ------------------------------------------------------------------
    # Fabric → Cognitive
    # ------------------------------------------------------------------

    def _subscribe_fabric_to_cognitive(self) -> None:
        try:
            from runtime.event_fabric import EventChannel, get_event_fabric

            def _on_governance(event: Any) -> Any:
                if event.event_type == "MODE_TRANSITION":
                    self._fabric_to_cog(event)
                try:
                    from runtime.event_fabric import EventAck
                    return EventAck(
                        event_sequence=event.sequence,
                        subscriber_id="cross_bus_router",
                        accepted=True,
                    )
                except Exception:
                    return None

            get_event_fabric().subscribe(
                EventChannel.GOVERNANCE,
                "cross_bus_router",
                _on_governance,
            )
        except Exception as exc:
            _logger.debug("CrossBusRouter._subscribe_fabric_to_cognitive error: %s", exc)

    def _fabric_to_cog(self, event: Any) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            payload = dict(getattr(event, "payload", {}))
            payload["source"] = "cross_bus_router"
            payload["event"] = event.event_type
            payload.setdefault("ts_ns", 0)
            get_event_bus().publish(CognitiveChannel.INDIRA_THOUGHT, payload)
            self._increment(f"fabric→cog:{event.event_type}")
        except Exception as exc:
            _logger.debug("CrossBusRouter._fabric_to_cog error: %s", exc)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _increment(self, key: str) -> None:
        with self._lock:
            self._routed_counts[key] = self._routed_counts.get(key, 0) + 1


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_router: CrossBusRouter | None = None
_router_lock = threading.Lock()


def get_cross_bus_router() -> CrossBusRouter:
    global _router
    with _router_lock:
        if _router is None:
            _router = CrossBusRouter()
    return _router


__all__ = [
    "CrossBusRouter",
    "get_cross_bus_router",
]
