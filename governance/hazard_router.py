"""governance.hazard_router — SYSTEM_HAZARD → EXECUTION_REQUEST Router.

Build Plan §5.2: Routes hazard events through classification and escalation
before transforming them into governance-approved execution requests.

Flow: HazardEvent → classify → escalate (if needed) → map to action
"""

from __future__ import annotations

import threading
from typing import Any

from governance.emergency_policy import get_snapshot
from state.ledger.risk_resolution_log import ResolutionRecord, get_risk_resolution_log


class HazardRouter:
    """Routes SYSTEM_HAZARD events to governance-approved actions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def route(
        self, hazard_type: str, severity: str, source: str, details: dict[str, Any] | None = None
    ) -> str:
        """Classify and route a hazard to an action string.

        Returns the action to execute (e.g. 'halt_trading', 'safe_mode').
        """
        from governance.escalation_matrix import escalate_severity, should_escalate
        from governance.hazard_classifier import classify

        classification = classify(hazard_type, severity)
        effective_severity = severity

        if should_escalate(hazard_type, severity):
            effective_severity = escalate_severity(severity)

        snapshot = get_snapshot()
        rule = snapshot.rules.get(hazard_type)
        if rule is None:
            action = snapshot.default_action
        else:
            _ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
            if _ORDER.get(effective_severity, 1) >= _ORDER.get(rule.severity_threshold, 2):
                action = rule.action
            else:
                action = "noop"

        get_risk_resolution_log().record(
            ResolutionRecord(
                hazard_type=hazard_type,
                action_taken=action,
                decided_by="hazard_router",
                severity=effective_severity,
                details={
                    "classification": classification,
                    "original_severity": severity,
                    **(details or {}),
                },
            )
        )
        return action


_router: HazardRouter | None = None
_lock = threading.Lock()


def get_hazard_router() -> HazardRouter:
    global _router
    if _router is None:
        with _lock:
            if _router is None:
                _router = HazardRouter()
    return _router
