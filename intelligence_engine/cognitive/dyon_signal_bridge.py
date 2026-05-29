"""DyonSignalBridge — DYON+Risk→INDIRA real-time cognitive coupling (P3 Reality Layer).

Subscribes to the cognitive event bus and translates DYON's architectural
health signals and risk breach signals into FeedbackSamples for INDIRA's
LearningPersistence.

Coupling logic:
    DYON_SCAN_COMPLETE:
        clean scan   → +0.3 reward to confidence_baseline (architecture healthy)
        warning only → ±0.0 (neutral, no action)
        critical ×1  → -0.4 reward (system under architectural stress)
        critical ×N  → -0.4 - 0.1*(N-1) capped at -0.9 (escalating penalty)

    DYON_PROPOSAL:
        CRITICAL severity proposal → -0.2 reward to confidence_baseline
        WARNING severity proposal  → -0.05 reward (minor penalty)

    RISK_BREACH:
        halted=True  → -0.5 reward to confidence_baseline (kill condition hit)
        halted=False → -0.15 reward (near-breach warning)

    These signals cause the slow-loop learner (every 20 IndiraRuntime ticks)
    to evolve confidence_baseline downward during periods of architectural
    instability or active risk limits, and recover when DYON reports clean scans.

Authority (B1): imports only from intelligence_engine.* and core.*.
state.event_bus is a state-tier module so it is permitted.
INV-15: ts_ns is embedded in every published payload.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

_logger = logging.getLogger(__name__)

_MAX_PENDING = 200   # cap on unprocessed feedback samples


class DyonSignalBridge:
    """Translates DYON event bus messages into LearningPersistence feedback.

    Operates in a thread-safe, non-blocking manner: DYON events are buffered
    in a local list and flushed into LearningPersistence each time
    ``flush(ts_ns)`` is called (from IndiraRuntime._try_learning_hook).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: list[tuple[str, float]] = []   # (parameter, reward)
        self._scan_events_received = 0
        self._proposal_events_received = 0
        self._risk_events_received = 0
        self._subscribed = False

    def activate(self) -> None:
        """Subscribe to the event bus.  Idempotent — safe to call multiple times."""
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
                "DyonSignalBridge: subscribed to DYON_SCAN_COMPLETE + DYON_PROPOSAL + RISK_BREACH"
            )
        except Exception as exc:
            _logger.debug("DyonSignalBridge.activate error: %s", exc)

    def flush(self, *, ts_ns: int) -> int:
        """Submit all buffered feedback samples to LearningPersistence.

        Returns the number of samples flushed.  Called from IndiraRuntime
        on the same cadence as the learning hook (every 20 ticks).
        """
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
                "DyonSignalBridge.flush: submitted %d samples to LearningPersistence",
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
            "scan_events_received": self._scan_events_received,
            "proposal_events_received": self._proposal_events_received,
            "risk_events_received": self._risk_events_received,
            "pending_feedback_samples": pending,
        }

    # ------------------------------------------------------------------
    # Event handlers (called from DYON's thread via the event bus)
    # ------------------------------------------------------------------

    def _on_scan_complete(self, payload: dict[str, Any]) -> None:
        """Translate a DYON_SCAN_COMPLETE event into a feedback sample."""
        self._scan_events_received += 1
        clean = bool(payload.get("clean", True))
        critical = int(payload.get("critical_count", 0))

        if clean:
            reward = 0.3
        elif critical == 0:
            reward = 0.0   # warnings only — neutral
        else:
            reward = max(-0.9, -0.4 - 0.1 * (critical - 1))

        with self._lock:
            if len(self._pending) < _MAX_PENDING:
                self._pending.append(("confidence_baseline", reward))

    def _on_proposal(self, payload: dict[str, Any]) -> None:
        """Translate a DYON_PROPOSAL event into a small confidence penalty."""
        self._proposal_events_received += 1
        severity = str(payload.get("severity", "WARNING")).upper()
        reward = -0.20 if severity == "CRITICAL" else -0.05

        with self._lock:
            if len(self._pending) < _MAX_PENDING:
                self._pending.append(("confidence_baseline", reward))

    def _on_risk_breach(self, payload: dict[str, Any]) -> None:
        """Translate a RISK_BREACH event into a confidence penalty.

        A kill condition (halted=True) is a strong signal to pull back;
        a near-breach (halted=False) is a softer warning.
        """
        self._risk_events_received += 1
        halted = bool(payload.get("halted", False))
        reward = -0.50 if halted else -0.15

        with self._lock:
            if len(self._pending) < _MAX_PENDING:
                self._pending.append(("confidence_baseline", reward))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_bridge: DyonSignalBridge | None = None
_bridge_lock = threading.Lock()


def get_dyon_signal_bridge() -> DyonSignalBridge:
    """Return the process-wide DyonSignalBridge singleton."""
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
