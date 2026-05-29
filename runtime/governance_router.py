"""runtime.governance_router — Governance Decision Router to Cognitive Subsystems.

Routes governance decisions and mode transitions from the execution fabric
to the cognitive subsystems (INDIRA and DYON), so both intelligences remain
aware of operator authority actions and system mode changes.

Routes:
  ExecutionFabric.GOVERNANCE / "MODE_TRANSITION"
    → INDIRA_THOUGHT  (INDIRA adjusts confidence based on new mode)
    → DYON_SCAN_COMPLETE  (DYON rescans after mode change, best-effort)

  ExecutionFabric.GOVERNANCE / "COGOV_CRITICAL_VIOLATION"
    → CognitiveChannel.INDIRA_THOUGHT  (INDIRA informed of integrity breach)

  ExecutionFabric.SYSTEM / "RISK_BREACH"
    → CognitiveChannel.RISK_BREACH  (if not already published by RiskTracker)

Operator override notifications are also published here so INDIRA's
confidence baseline adjusts when the operator intervenes.

Authority: runtime tier — imports state.*, runtime.*. Never execution_engine.
INV-15: ts_ns sourced from fabric events.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

_logger = logging.getLogger(__name__)

# Mode → confidence multiplier for INDIRA's baseline
_MODE_CONFIDENCE_IMPACT: dict[str, float] = {
    "PAPER":   0.0,   # neutral — research phase
    "SAFE":   -0.30,  # cognitive distress — violation drove safe mode
    "LIVE":    0.0,   # live mode: operator authorized — neutral impact
    "HALTED": -0.50,  # severe suppression — system halted
}


class GovernanceRouter:
    """Routes governance decisions to cognitive subsystems."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._routes_fired: dict[str, int] = {}

    def activate(self) -> None:
        """Subscribe to governance fabric channels.  Idempotent."""
        with self._lock:
            if self._active:
                return
            self._active = True

        self._subscribe_fabric()
        _logger.info("GovernanceRouter: activated")

    def notify_operator_override(self, reason: str, ts_ns: int) -> None:
        """Publish an operator override notification to cognitive subsystems.

        Called when the operator intervenes directly (e.g., manual mode change,
        forced halt, strategy veto).  Both intelligences should know.
        """
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.INDIRA_THOUGHT, {
                "source": "governance_router",
                "event": "OPERATOR_OVERRIDE",
                "reason": reason,
                "ts_ns": ts_ns,
            })
        except Exception as exc:
            _logger.debug("GovernanceRouter.notify_operator_override error: %s", exc)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active": self._active,
                "routes_fired": dict(self._routes_fired),
                "total_routed": sum(self._routes_fired.values()),
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _subscribe_fabric(self) -> None:
        try:
            from runtime.event_fabric import EventChannel, get_event_fabric

            def _on_governance(event: Any) -> Any:
                self._handle_governance(event)
                try:
                    from runtime.event_fabric import EventAck
                    return EventAck(
                        event_sequence=event.sequence,
                        subscriber_id="governance_router",
                        accepted=True,
                    )
                except Exception:
                    return None

            get_event_fabric().subscribe(
                EventChannel.GOVERNANCE,
                "governance_router",
                _on_governance,
            )
            _logger.debug("GovernanceRouter: subscribed to GOVERNANCE channel")
        except Exception as exc:
            _logger.debug("GovernanceRouter._subscribe_fabric error: %s", exc)

    def _handle_governance(self, event: Any) -> None:
        event_type = getattr(event, "event_type", "")
        payload = dict(getattr(event, "payload", {}))
        ts_ns = int(payload.get("ts_ns", 0))

        if event_type == "MODE_TRANSITION":
            self._on_mode_transition(payload, ts_ns)
        elif event_type == "COGOV_CRITICAL_VIOLATION":
            self._on_cogov_violation(payload, ts_ns)

    def _on_mode_transition(self, payload: dict[str, Any], ts_ns: int) -> None:
        new_mode = str(payload.get("new_mode", ""))
        old_mode = str(payload.get("old_mode", ""))
        confidence_delta = _MODE_CONFIDENCE_IMPACT.get(new_mode, 0.0)

        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.INDIRA_THOUGHT, {
                "source": "governance_router",
                "event": "MODE_TRANSITION",
                "old_mode": old_mode,
                "new_mode": new_mode,
                "confidence_delta": confidence_delta,
                "ts_ns": ts_ns,
            })
        except Exception:
            pass

        # If transitioning to SAFE or HALTED, also nudge DYON to rescan
        if new_mode in ("SAFE", "HALTED"):
            try:
                from state.event_bus import CognitiveChannel, get_event_bus
                get_event_bus().publish(CognitiveChannel.DYON_SCAN_COMPLETE, {
                    "source": "governance_router",
                    "trigger": "mode_transition",
                    "new_mode": new_mode,
                    "ts_ns": ts_ns,
                    "scan_count": 0,
                    "violation_count": 0,
                    "clean": False,
                })
            except Exception:
                pass

        self._increment(f"mode_transition:{old_mode}→{new_mode}")

    def _on_cogov_violation(self, payload: dict[str, Any], ts_ns: int) -> None:
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.INDIRA_THOUGHT, {
                "source": "governance_router",
                "event": "COGOV_CRITICAL_VIOLATION",
                "violation": str(payload.get("violation", "")),
                "guard": str(payload.get("guard", "")),
                "ts_ns": ts_ns,
            })
        except Exception:
            pass
        self._increment("cogov_violation")

    def _increment(self, key: str) -> None:
        with self._lock:
            self._routes_fired[key] = self._routes_fired.get(key, 0) + 1


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_router: GovernanceRouter | None = None
_router_lock = threading.Lock()


def get_governance_router() -> GovernanceRouter:
    global _router
    with _router_lock:
        if _router is None:
            _router = GovernanceRouter()
    return _router


__all__ = [
    "GovernanceRouter",
    "get_governance_router",
]
