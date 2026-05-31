"""governance.market_context_projector — Dyon/Risk → GOVERNED_MARKET_CONTEXT.

Manifest §5 (Cognitive Expansion): the only SYSTEM→MARKET pathway is
governance-mediated read-only context for INDIRA learning feedback.

Subscribes to raw cognitive bus channels on the governance side, validates
payloads, and republishes ``CognitiveChannel.GOVERNED_MARKET_CONTEXT`` for
``intelligence_engine.cognitive.dyon_signal_bridge``.

Authority: governance.* + state.event_bus + core.* only.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

_logger = logging.getLogger(__name__)


class MarketContextProjector:
    """Projects Dyon and risk signals into governance-gated market context."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribed = False
        self._projected_count = 0
        self._suppressed_count = 0

    def activate(self) -> None:
        if self._subscribed:
            return
        try:
            from state.event_bus import CognitiveChannel, get_event_bus

            bus = get_event_bus()
            bus.subscribe(CognitiveChannel.DYON_SCAN_COMPLETE, self._on_scan_complete)
            bus.subscribe(CognitiveChannel.DYON_PROPOSAL, self._on_proposal)
            bus.subscribe(CognitiveChannel.RISK_BREACH, self._on_risk_breach)
            self._subscribed = True
            _logger.info(
                "MarketContextProjector: listening for DYON/RISK → GOVERNED_MARKET_CONTEXT"
            )
        except Exception as exc:
            _logger.debug("MarketContextProjector.activate error: %s", exc)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "subscribed": self._subscribed,
                "projected_count": self._projected_count,
                "suppressed_count": self._suppressed_count,
            }

    def _publish(self, *, source_kind: str, payload: dict[str, Any]) -> None:
        ts_ns = int(payload.get("ts_ns", 0))
        if ts_ns <= 0:
            with self._lock:
                self._suppressed_count += 1
            return
        out = {
            "source_kind": source_kind,
            "governed": True,
            "ts_ns": ts_ns,
            **payload,
        }
        try:
            from state.event_bus import CognitiveChannel, get_event_bus

            get_event_bus().publish(CognitiveChannel.GOVERNED_MARKET_CONTEXT, out)
            with self._lock:
                self._projected_count += 1
        except Exception as exc:
            _logger.debug("MarketContextProjector._publish error: %s", exc)

    def _on_scan_complete(self, payload: dict[str, Any]) -> None:
        self._publish(source_kind="DYON_SCAN_COMPLETE", payload=dict(payload))

    def _on_proposal(self, payload: dict[str, Any]) -> None:
        self._publish(source_kind="DYON_PROPOSAL", payload=dict(payload))

    def _on_risk_breach(self, payload: dict[str, Any]) -> None:
        self._publish(source_kind="RISK_BREACH", payload=dict(payload))


_projector: MarketContextProjector | None = None
_projector_lock = threading.Lock()


def get_market_context_projector() -> MarketContextProjector:
    global _projector
    with _projector_lock:
        if _projector is None:
            _projector = MarketContextProjector()
            _projector.activate()
    return _projector


__all__ = ["MarketContextProjector", "get_market_context_projector"]
