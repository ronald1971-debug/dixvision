"""Governed market context bridge (legacy name: DyonSignalBridge).

Manifest §5: INDIRA consumes only ``GOVERNED_MARKET_CONTEXT`` published by
``governance.market_context_projector`` — never raw DYON or RISK bus channels.

Translates governed payloads into FeedbackSamples for LearningPersistence.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

_logger = logging.getLogger(__name__)

_MAX_PENDING = 200


class DyonSignalBridge:
    """INDIRA-side consumer of governance-gated market context."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: list[tuple[str, float]] = []
        self._governed_events_received = 0
        self._subscribed = False

    def activate(self) -> None:
        if self._subscribed:
            return
        try:
            from state.event_bus import CognitiveChannel, get_event_bus

            bus = get_event_bus()
            bus.subscribe(
                CognitiveChannel.GOVERNED_MARKET_CONTEXT,
                self._on_governed_context,
            )
            self._subscribed = True
            _logger.info(
                "DyonSignalBridge: subscribed to GOVERNED_MARKET_CONTEXT only"
            )
        except Exception as exc:
            _logger.debug("DyonSignalBridge.activate error: %s", exc)

    def flush(self, *, ts_ns: int) -> int:
        with self._lock:
            pending = list(self._pending)
            self._pending.clear()
        if not pending:
            return 0
        try:
            from intelligence_engine.learning.learning_persistence import (
                get_learning_persistence,
            )

            lp = get_learning_persistence()
            for parameter, reward in pending:
                lp.submit_feedback(parameter, reward, ts_ns=ts_ns)
            _logger.debug(
                "DyonSignalBridge.flush: submitted %d governed samples",
                len(pending),
            )
        except Exception as exc:
            _logger.debug("DyonSignalBridge.flush error: %s", exc)
        return len(pending)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            pending = len(self._pending)
        return {
            "subscribed": self._subscribed,
            "channel": "GOVERNED_MARKET_CONTEXT",
            "governed_events_received": self._governed_events_received,
            "pending_feedback_samples": pending,
        }

    def _on_governed_context(self, payload: dict[str, Any]) -> None:
        if not payload.get("governed"):
            return
        self._governed_events_received += 1
        reward = self._reward_for_payload(payload)
        with self._lock:
            if len(self._pending) < _MAX_PENDING:
                self._pending.append(("confidence_baseline", reward))

    def _reward_for_payload(self, payload: dict[str, Any]) -> float:
        kind = str(payload.get("source_kind", ""))
        if kind == "DYON_SCAN_COMPLETE":
            clean = bool(payload.get("clean", True))
            critical = int(payload.get("critical_count", 0))
            if clean:
                return 0.3
            if critical == 0:
                return 0.0
            return max(-0.9, -0.4 - 0.1 * (critical - 1))
        if kind == "DYON_PROPOSAL":
            severity = str(payload.get("severity", "WARNING")).upper()
            return -0.20 if severity == "CRITICAL" else -0.05
        if kind == "RISK_BREACH":
            halted = bool(payload.get("halted", False))
            return -0.50 if halted else -0.15
        return 0.0


_bridge: DyonSignalBridge | None = None
_bridge_lock = threading.Lock()


def get_dyon_signal_bridge() -> DyonSignalBridge:
    global _bridge
    with _bridge_lock:
        if _bridge is None:
            _bridge = DyonSignalBridge()
            _bridge.activate()
    return _bridge


__all__ = [
    "DyonSignalBridge",
    "get_dyon_signal_bridge",
]
