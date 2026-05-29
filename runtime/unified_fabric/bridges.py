"""runtime.unified_fabric.bridges — Event bus bridges.

Each bridge subscribes to one existing event system and re-publishes
every event into the CentralBusAuthority as a UnifiedEvent.

This is additive — existing buses remain untouched. The bridges are
pure observers: they never modify payloads or delivery of the original
event, they only forward a copy to the unified fabric.

Bridges:
  CognitiveBusBridge   — CognitiveEventBus (state.event_bus) → unified
  ExecutionFabricBridge — EventFabric (runtime.event_fabric) → unified
  LedgerBridge         — ledger event_store writes → unified (best-effort)

All bridges activate lazily and never raise to callers.
INV-15: ts_ns is read from each event payload (publisher-supplied).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from runtime.unified_fabric.contracts import FabricDomain, FabricPriority

_logger = logging.getLogger(__name__)

# Mapping from CognitiveChannel name → (FabricDomain, FabricPriority)
_COGNITIVE_MAP: dict[str, tuple[FabricDomain, FabricPriority]] = {
    "dyon_violation":    (FabricDomain.COGNITIVE, FabricPriority.HIGH),
    "dyon_proposal":     (FabricDomain.EVOLUTION, FabricPriority.HIGH),
    "dyon_scan_complete":(FabricDomain.COGNITIVE, FabricPriority.NORMAL),
    "indira_thought":    (FabricDomain.COGNITIVE, FabricPriority.NORMAL),
    "indira_insight":    (FabricDomain.COGNITIVE, FabricPriority.HIGH),
    "research_complete": (FabricDomain.RESEARCH,  FabricPriority.HIGH),
    "market_tick":       (FabricDomain.MARKET,    FabricPriority.NORMAL),
    "risk_breach":       (FabricDomain.GOVERNANCE, FabricPriority.CRITICAL),
}

# Mapping from EventChannel name → FabricDomain
_FABRIC_MAP: dict[str, FabricDomain] = {
    "MARKET":     FabricDomain.MARKET,
    "SIGNAL":     FabricDomain.COGNITIVE,
    "GOVERNANCE": FabricDomain.GOVERNANCE,
    "EXECUTION":  FabricDomain.EXECUTION,
    "SYSTEM":     FabricDomain.SYSTEM,
    "AUDIT":      FabricDomain.AUDIT,
}


class CognitiveBusBridge:
    """Subscribes to all CognitiveChannel channels, forwards to unified fabric."""

    def __init__(self) -> None:
        self._lock    = threading.Lock()
        self._active  = False
        self._routed: dict[str, int] = {}

    def activate(self) -> None:
        with self._lock:
            if self._active:
                return
            self._active = True

        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            bus = get_event_bus()
            for channel in CognitiveChannel:
                ch_name = channel.value
                def _make_handler(ch: str):
                    def _handler(payload: dict[str, Any]) -> None:
                        self._forward(ch, payload)
                    return _handler
                bus.subscribe(channel, _make_handler(ch_name))
            _logger.info("CognitiveBusBridge: activated (%d channels)", len(CognitiveChannel))
        except Exception as exc:
            _logger.debug("CognitiveBusBridge.activate error: %s", exc)

    def _forward(self, channel_name: str, payload: dict[str, Any]) -> None:
        try:
            from runtime.unified_fabric.authority import get_central_bus_authority
            domain, priority = _COGNITIVE_MAP.get(
                channel_name, (FabricDomain.COGNITIVE, FabricPriority.NORMAL)
            )
            ts_ns = int(payload.get("ts_ns", time.time_ns()))
            bus   = get_central_bus_authority()
            bus.publish(
                domain     = domain,
                event_type = channel_name.upper(),
                ts_ns      = ts_ns,
                source     = f"cognitive_bus.{channel_name}",
                payload    = {k: str(v) for k, v in payload.items()},
                priority   = priority,
                tags       = frozenset(["cognitive", "bridged", channel_name]),
            )
            with self._lock:
                self._routed[channel_name] = self._routed.get(channel_name, 0) + 1
        except Exception as exc:
            _logger.debug("CognitiveBusBridge._forward[%s] error: %s", channel_name, exc)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active":  self._active,
                "routed":  dict(self._routed),
                "total":   sum(self._routed.values()),
            }


class ExecutionFabricBridge:
    """Subscribes to all EventFabric channels, forwards to unified fabric."""

    def __init__(self) -> None:
        self._lock    = threading.Lock()
        self._active  = False
        self._routed: dict[str, int] = {}

    def activate(self) -> None:
        with self._lock:
            if self._active:
                return
            self._active = True

        try:
            from runtime.event_fabric import EventChannel, get_event_fabric
            fabric = get_event_fabric()
            for channel in EventChannel:
                ch_name = channel.value
                domain  = _FABRIC_MAP.get(ch_name, FabricDomain.UNKNOWN)
                def _make_handler(ch: str, dom: FabricDomain):
                    def _handler(event: Any) -> None:
                        self._forward(ch, dom, event)
                    return _handler
                fabric.subscribe(channel, f"unified_bridge_{ch_name}", _make_handler(ch_name, domain))
            _logger.info("ExecutionFabricBridge: activated (%d channels)", len(EventChannel))
        except Exception as exc:
            _logger.debug("ExecutionFabricBridge.activate error: %s", exc)

    def _forward(self, channel_name: str, domain: FabricDomain, fabric_event: Any) -> None:
        try:
            from runtime.unified_fabric.authority import get_central_bus_authority
            ts_ns = int(getattr(fabric_event, "ts_ns", time.time_ns()))
            event_type = str(getattr(fabric_event, "event_type", channel_name))
            source = str(getattr(fabric_event, "source", f"exec_fabric.{channel_name}"))
            trace_id = str(getattr(fabric_event, "trace_id", ""))
            payload_raw = getattr(fabric_event, "payload", {})
            payload = {k: str(v) for k, v in (payload_raw.items() if hasattr(payload_raw, "items") else {})}

            bus = get_central_bus_authority()
            bus.publish(
                domain     = domain,
                event_type = event_type,
                ts_ns      = ts_ns or time.time_ns(),
                source     = source,
                payload    = payload,
                trace_id   = trace_id,
                tags       = frozenset(["execution", "bridged", channel_name.lower()]),
            )
            with self._lock:
                self._routed[channel_name] = self._routed.get(channel_name, 0) + 1
        except Exception as exc:
            _logger.debug("ExecutionFabricBridge._forward[%s] error: %s", channel_name, exc)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active": self._active,
                "routed": dict(self._routed),
                "total":  sum(self._routed.values()),
            }


# --------------------------------------------------------------------------
# Singleton accessors
# --------------------------------------------------------------------------

_cog_bridge:  CognitiveBusBridge   | None = None
_exec_bridge: ExecutionFabricBridge | None = None
_b_lock = threading.Lock()


def get_cognitive_bus_bridge() -> CognitiveBusBridge:
    global _cog_bridge
    if _cog_bridge is None:
        with _b_lock:
            if _cog_bridge is None:
                _cog_bridge = CognitiveBusBridge()
    return _cog_bridge


def get_execution_fabric_bridge() -> ExecutionFabricBridge:
    global _exec_bridge
    if _exec_bridge is None:
        with _b_lock:
            if _exec_bridge is None:
                _exec_bridge = ExecutionFabricBridge()
    return _exec_bridge


__all__ = [
    "CognitiveBusBridge",
    "ExecutionFabricBridge",
    "get_cognitive_bus_bridge",
    "get_execution_fabric_bridge",
]
