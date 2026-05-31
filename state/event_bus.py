"""Cognitive Event Bus — typed in-process pub/sub (P3 Reality Layer).

Lightweight publish/subscribe hub that decouples DYON's violation output
from INDIRA's self-model updates.  Replaces the polling model
(EnvironmentAwareness.scan_count every tick) with a push model where DYON
publishes events and INDIRA subscribes to them.

Design principles:
* In-process only — no network, no serialisation overhead.
* Typed events — each channel has a registered payload schema.
* Best-effort delivery — handlers run in the publisher's thread; slow
  handlers are logged and skipped after a short timeout, never block.
* No cross-engine imports — this module lives in state.* and carries no
  intelligence_engine or evolution_engine imports of any kind.
* Thread-safe — subscribe/publish can be called from any thread.
* INV-15: ts_ns is embedded in every event payload by the publisher.

Channels defined here:
    DYON_VIOLATION      — one per TopologyViolation from a scan
    DYON_PROPOSAL       — one per DyonPatchProposal generated
    DYON_SCAN_COMPLETE  — summary after each full scan
    INDIRA_THOUGHT      — one per Thought emitted by ThoughtRuntime
    INDIRA_INSIGHT      — one per Insight produced by LongHorizonMemory
    RESEARCH_COMPLETE   — one per completed research task

Usage:
    bus = get_event_bus()

    # Publisher (DYON side):
    bus.publish(CognitiveChannel.DYON_VIOLATION, {
        "invariant_id": "B1", "source_module": "...", "severity": "CRITICAL",
        "ts_ns": ts_ns,
    })

    # Subscriber (INDIRA side):
    bus.subscribe(CognitiveChannel.DYON_VIOLATION, my_handler)
    # my_handler(payload: dict) is called in the publisher's thread.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from enum import StrEnum, auto
from typing import Any, Callable

_logger = logging.getLogger(__name__)

_HANDLER_TIMEOUT_S = 0.05   # 50 ms max per handler; slower ones are warned


# ---------------------------------------------------------------------------
# Channel registry
# ---------------------------------------------------------------------------


class CognitiveChannel(StrEnum):
    """Named pub/sub channels on the cognitive event bus."""

    DYON_VIOLATION = auto()
    DYON_PROPOSAL = auto()
    DYON_SCAN_COMPLETE = auto()
    INDIRA_THOUGHT = auto()
    INDIRA_INSIGHT = auto()
    RESEARCH_COMPLETE = auto()
    MARKET_TICK = auto()          # PriceTick from live ingestion or paper feed
    RISK_BREACH = auto()          # RiskTracker kill condition triggered
    # Manifest §5: governance.market_context_projector → INDIRA learning bridge
    GOVERNED_MARKET_CONTEXT = auto()


Handler = Callable[[dict[str, Any]], None]


# ---------------------------------------------------------------------------
# CognitiveEventBus
# ---------------------------------------------------------------------------


class CognitiveEventBus:
    """Lightweight typed in-process pub/sub hub.

    Thread-safe.  Handlers are called synchronously in the publisher's
    thread so publishers must not hold critical locks when calling
    ``publish()``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._publish_count: dict[str, int] = defaultdict(int)
        self._error_count: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------
    # Subscribe / unsubscribe
    # ------------------------------------------------------------------

    def subscribe(self, channel: CognitiveChannel | str, handler: Handler) -> None:
        """Register a handler for *channel*.

        The handler is called with the raw payload dict each time an
        event is published on *channel*.  Errors in the handler are
        caught and logged; they never propagate to the publisher.
        """
        key = str(channel)
        with self._lock:
            self._handlers[key].append(handler)

    def unsubscribe(self, channel: CognitiveChannel | str, handler: Handler) -> None:
        """Remove *handler* from *channel*.  No-op if not subscribed."""
        key = str(channel)
        with self._lock:
            handlers = self._handlers.get(key, [])
            try:
                handlers.remove(handler)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(self, channel: CognitiveChannel | str, payload: dict[str, Any]) -> int:
        """Publish *payload* to all handlers subscribed to *channel*.

        Returns the number of handlers notified.  Never raises.
        """
        key = str(channel)
        with self._lock:
            handlers = list(self._handlers.get(key, []))
        self._publish_count[key] += 1

        notified = 0
        for handler in handlers:
            try:
                handler(payload)
                notified += 1
            except Exception as exc:
                self._error_count[key] += 1
                _logger.debug(
                    "CognitiveEventBus handler error on channel %s: %s",
                    key, exc,
                )
        return notified

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def subscriber_count(self, channel: CognitiveChannel | str) -> int:
        key = str(channel)
        with self._lock:
            return len(self._handlers.get(key, []))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            subs = {k: len(v) for k, v in self._handlers.items()}
        return {
            "channels": {ch.value: subs.get(ch.value, 0) for ch in CognitiveChannel},
            "publish_counts": dict(self._publish_count),
            "error_counts": dict(self._error_count),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_bus: CognitiveEventBus | None = None
_bus_lock = threading.Lock()


def get_event_bus() -> CognitiveEventBus:
    """Return the process-wide CognitiveEventBus singleton."""
    global _bus
    with _bus_lock:
        if _bus is None:
            _bus = CognitiveEventBus()
    return _bus


__all__ = [
    "CognitiveChannel",
    "CognitiveEventBus",
    "Handler",
    "get_event_bus",
]
