"""runtime.unified_fabric.authority — CentralBusAuthority.

The authoritative singleton router for the Unified Event Fabric.
All events from all domains flow through here before delivery.

Responsibilities:
1. Assign stable event_id (SHA-256 of domain+type+ts_ns+source)
2. Assign monotonic global sequence number
3. Assign/propagate trace_id (inherit from parent or generate new)
4. Register subscribers per domain+event_type
5. Route events to matching subscribers
6. Emit to EventTracer, EventLineageGraph, FabricPersistence

Design:
- Never raises to publishers (all delivery is best-effort)
- Thread-safe via a single dispatch lock
- No engine imports (runtime tier only)
- INV-15: all ts_ns come from the event, never from wall clock
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import defaultdict
from typing import Any, Callable

from runtime.unified_fabric.contracts import (
    CausalLink,
    FabricDomain,
    FabricPriority,
    UnifiedEvent,
)

_logger = logging.getLogger(__name__)

Handler = Callable[[UnifiedEvent], None]

_WILDCARD = "*"   # subscribe to all event_types within a domain


class CentralBusAuthority:
    """Global singleton event router for the Unified Event Fabric.

    All subsystems publish here; all consumers subscribe here.
    The existing CognitiveEventBus and EventFabric remain intact —
    bridges forward their events into this authority.
    """

    def __init__(self) -> None:
        self._lock          = threading.Lock()
        self._sequence:     int = 0
        self._active:       bool = False

        # subscribers: (domain, event_type|"*") → list[handler]
        self._subs:         dict[tuple[str, str], list[Handler]] = defaultdict(list)

        # sidecars (activated subsystems that receive every event)
        self._tracer:       Any = None
        self._lineage:      Any = None
        self._persistence:  Any = None

        # stats
        self._published:    int = 0
        self._delivered:    int = 0
        self._errors:       int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def activate(
        self,
        *,
        tracer:      Any = None,
        lineage:     Any = None,
        persistence: Any = None,
    ) -> None:
        """Wire sidecars. Idempotent."""
        with self._lock:
            if tracer is not None:
                self._tracer = tracer
            if lineage is not None:
                self._lineage = lineage
            if persistence is not None:
                self._persistence = persistence
            self._active = True

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        domain: FabricDomain | str,
        handler: Handler,
        *,
        event_type: str = _WILDCARD,
    ) -> None:
        """Register handler for (domain, event_type) or all types."""
        key = (str(domain), event_type)
        with self._lock:
            self._subs[key].append(handler)

    def unsubscribe(
        self,
        domain: FabricDomain | str,
        handler: Handler,
        *,
        event_type: str = _WILDCARD,
    ) -> None:
        key = (str(domain), event_type)
        with self._lock:
            subs = self._subs.get(key, [])
            try:
                subs.remove(handler)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Publish
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
        """Wrap, sequence, route, and persist one event.

        Returns the UnifiedEvent, or None on construction failure.
        Never raises.
        """
        try:
            with self._lock:
                self._sequence += 1
                seq = self._sequence

            event_id = self._make_id(domain, event_type, ts_ns, source, seq)
            tid = trace_id or self._new_trace_id(event_id)

            event = UnifiedEvent(
                event_id   = event_id,
                domain     = domain,
                event_type = event_type,
                ts_ns      = ts_ns,
                source     = source,
                payload    = payload,
                priority   = priority,
                sequence   = seq,
                trace_id   = tid,
                parent_id  = parent_id,
                tags       = tags or frozenset(),
            )

            # Sidecars (non-blocking)
            self._sidecar_trace(event)
            self._sidecar_persist(event)

            # Route to subscribers
            self._route(event)

            with self._lock:
                self._published += 1

            return event

        except Exception as exc:
            with self._lock:
                self._errors += 1
            _logger.debug("CentralBusAuthority.publish error: %s", exc)
            return None

    def record_causality(
        self,
        *,
        cause_id:  str,
        effect_id: str,
        ts_ns:     int,
        kind:      str = "",
    ) -> None:
        """Record a causal link between two events."""
        if self._lineage is None:
            return
        try:
            link = CausalLink(
                cause_id=cause_id,
                effect_id=effect_id,
                ts_ns=ts_ns,
                kind=kind,
            )
            self._lineage.record(link)
        except Exception as exc:
            _logger.debug("CentralBusAuthority.record_causality error: %s", exc)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        with self._lock:
            subs_by_domain: dict[str, int] = defaultdict(int)
            for (domain, _), handlers in self._subs.items():
                subs_by_domain[domain] += len(handlers)
            return {
                "active":      self._active,
                "sequence":    self._sequence,
                "published":   self._published,
                "delivered":   self._delivered,
                "errors":      self._errors,
                "subscribers": dict(subs_by_domain),
                "tracer":      self._tracer is not None,
                "lineage":     self._lineage is not None,
                "persistence": self._persistence is not None,
            }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _route(self, event: UnifiedEvent) -> None:
        """Deliver event to all matching subscribers."""
        domain_str = str(event.domain)
        with self._lock:
            # wildcard + specific type
            handlers = list(self._subs.get((domain_str, _WILDCARD), []))
            handlers += list(self._subs.get((domain_str, event.event_type), []))
            # global wildcard
            handlers += list(self._subs.get((_WILDCARD, _WILDCARD), []))

        for handler in handlers:
            try:
                handler(event)
                with self._lock:
                    self._delivered += 1
            except Exception as exc:
                with self._lock:
                    self._errors += 1
                _logger.debug(
                    "CentralBusAuthority handler error [%s/%s]: %s",
                    event.domain, event.event_type, exc,
                )

    def _sidecar_trace(self, event: UnifiedEvent) -> None:
        if self._tracer is None:
            return
        try:
            self._tracer.record(event)
        except Exception:
            pass

    def _sidecar_persist(self, event: UnifiedEvent) -> None:
        if self._persistence is None:
            return
        try:
            self._persistence.append(event)
        except Exception:
            pass

    @staticmethod
    def _make_id(
        domain: FabricDomain,
        event_type: str,
        ts_ns: int,
        source: str,
        seq: int,
    ) -> str:
        raw    = f"{domain}|{event_type}|{ts_ns}|{source}|{seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
        return f"uf-{domain.value[:3].lower()}-{digest}"

    @staticmethod
    def _new_trace_id(event_id: str) -> str:
        return "tr-" + hashlib.sha256(event_id.encode()).hexdigest()[:16]


_singleton: CentralBusAuthority | None = None
_lock = threading.Lock()


def get_central_bus_authority() -> CentralBusAuthority:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = CentralBusAuthority()
    return _singleton


__all__ = ["CentralBusAuthority", "Handler", "get_central_bus_authority"]
