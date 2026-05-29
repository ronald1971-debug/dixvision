"""runtime.unified_fabric.unified — UnifiedEventFabric.

Top-level coordinator for the Unified Event Fabric (Stage 5).

This is the circulatory system of DixVision — all events from all
domains flow through here, gaining:
  - Global sequence numbers (total order across domains)
  - Stable event IDs (SHA-256 deterministic)
  - Trace ID propagation (causal chain correlation)
  - Event lineage tracking (which event caused which)
  - Write-ahead SQLite persistence (replay-safe)
  - Cross-domain subscriber routing

Boot sequence:
  1. FabricPersistence — write-ahead log
  2. EventTracer       — span recording
  3. EventLineageGraph — causality tracking
  4. CentralBusAuthority — wire sidecars, activate router
  5. CognitiveBusBridge — tap CognitiveEventBus
  6. ExecutionFabricBridge — tap EventFabric

After activation, all existing event buses continue operating
normally — the bridges observe without interfering.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from runtime.unified_fabric.contracts import FabricDomain, FabricPriority, UnifiedEvent

_logger = logging.getLogger(__name__)

Handler = Callable[[UnifiedEvent], None]


class UnifiedEventFabric:
    """Top-level coordinator — activates all subsystems and exposes
    a unified publish/subscribe/replay surface."""

    def __init__(self) -> None:
        self._lock    = threading.Lock()
        self._active  = False

        # subsystems (lazily loaded at activate())
        self._persistence: Any = None
        self._tracer:      Any = None
        self._lineage:     Any = None
        self._authority:   Any = None
        self._cog_bridge:  Any = None
        self._exec_bridge: Any = None
        self._replay:      Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Boot all subsystems in order. Idempotent."""
        with self._lock:
            if self._active:
                return

        try:
            _logger.info("UnifiedEventFabric: activating...")

            # 1 — persistence (must be first — write-ahead)
            from runtime.unified_fabric.persistence import get_fabric_persistence
            self._persistence = get_fabric_persistence()
            _logger.info("  [1/7] FabricPersistence online")

            # 2 — tracer
            from runtime.unified_fabric.tracing import get_event_tracer
            self._tracer = get_event_tracer()
            _logger.info("  [2/7] EventTracer online")

            # 3 — lineage
            from runtime.unified_fabric.lineage import get_event_lineage_graph
            self._lineage = get_event_lineage_graph()
            _logger.info("  [3/7] EventLineageGraph online")

            # 4 — central authority (wire sidecars)
            from runtime.unified_fabric.authority import get_central_bus_authority
            self._authority = get_central_bus_authority()
            self._authority.activate(
                tracer      = self._tracer,
                lineage     = self._lineage,
                persistence = self._persistence,
            )
            _logger.info("  [4/7] CentralBusAuthority online")

            # 5 — cognitive bus bridge
            from runtime.unified_fabric.bridges import get_cognitive_bus_bridge
            self._cog_bridge = get_cognitive_bus_bridge()
            self._cog_bridge.activate()
            _logger.info("  [5/7] CognitiveBusBridge online")

            # 6 — execution fabric bridge
            from runtime.unified_fabric.bridges import get_execution_fabric_bridge
            self._exec_bridge = get_execution_fabric_bridge()
            self._exec_bridge.activate()
            _logger.info("  [6/7] ExecutionFabricBridge online")

            # 7 — replay stream
            from runtime.unified_fabric.replay import get_fabric_replay_stream
            self._replay = get_fabric_replay_stream()
            _logger.info("  [7/7] FabricReplayStream online")

            with self._lock:
                self._active = True
            _logger.info("UnifiedEventFabric: ALL 7 SUBSYSTEMS ONLINE")

        except Exception as exc:
            _logger.warning("UnifiedEventFabric.activate error: %s", exc)

    # ------------------------------------------------------------------
    # Publish API (convenience wrap over CentralBusAuthority)
    # ------------------------------------------------------------------

    def publish(
        self,
        *,
        domain:     FabricDomain,
        event_type: str,
        ts_ns:      int,
        source:     str,
        payload:    dict[str, Any],
        priority:   FabricPriority = FabricPriority.NORMAL,
        trace_id:   str = "",
        parent_id:  str = "",
        tags:       frozenset[str] | None = None,
    ) -> UnifiedEvent | None:
        """Publish an event into the unified fabric. Best-effort."""
        if not self._active or self._authority is None:
            return None
        return self._authority.publish(
            domain     = domain,
            event_type = event_type,
            ts_ns      = ts_ns,
            source     = source,
            payload    = payload,
            priority   = priority,
            trace_id   = trace_id,
            parent_id  = parent_id,
            tags       = tags,
        )

    def subscribe(
        self,
        domain:  FabricDomain | str,
        handler: Handler,
        *,
        event_type: str = "*",
    ) -> None:
        if self._authority is not None:
            self._authority.subscribe(domain, handler, event_type=event_type)

    def record_causality(
        self,
        *,
        cause_id:  str,
        effect_id: str,
        ts_ns:     int,
        kind:      str = "",
    ) -> None:
        if self._authority is not None:
            self._authority.record_causality(
                cause_id=cause_id, effect_id=effect_id, ts_ns=ts_ns, kind=kind
            )

    # ------------------------------------------------------------------
    # Replay surface
    # ------------------------------------------------------------------

    def start_replay(
        self,
        *,
        session_id:  str,
        since_ns:    int,
        until_ns:    int,
        domain:      str | None = None,
        event_type:  str | None = None,
        trace_id:    str | None = None,
    ):
        """Start a deterministic replay session. Returns a ReplaySession."""
        if self._replay is None:
            return None
        return self._replay.start(
            session_id  = session_id,
            since_ns    = since_ns,
            until_ns    = until_ns,
            domain      = domain,
            event_type  = event_type,
            trace_id    = trace_id,
        )

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active = self._active

        return {
            "active":      active,
            "authority":   self._authority.snapshot()   if self._authority   else None,
            "tracer":      self._tracer.snapshot()      if self._tracer      else None,
            "lineage":     self._lineage.snapshot()     if self._lineage     else None,
            "persistence": self._persistence.snapshot() if self._persistence else None,
            "cog_bridge":  self._cog_bridge.snapshot()  if self._cog_bridge  else None,
            "exec_bridge": self._exec_bridge.snapshot() if self._exec_bridge else None,
            "replay":      self._replay.snapshot()      if self._replay      else None,
        }


_singleton: UnifiedEventFabric | None = None
_lock = threading.Lock()


def get_unified_event_fabric() -> UnifiedEventFabric:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = UnifiedEventFabric()
    return _singleton


__all__ = ["UnifiedEventFabric", "get_unified_event_fabric"]
