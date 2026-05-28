"""governance.escalation_matrix — Hazard Severity Escalation Rules.

Build Plan §5.2: Determines when a hazard's severity should be escalated
based on type, recurrence, or compound conditions.
"""

from __future__ import annotations

_SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
_SEVERITY_NAMES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

_AUTO_ESCALATE_TYPES = frozenset(
    {
        "DATA_CORRUPTION_SUSPECTED",
        "LEDGER_INCONSISTENCY",
        "INTEGRITY_BREACH",
    }
)

_ESCALATE_ON_HIGH = frozenset(
    {
        "EXCHANGE_TIMEOUT",
        "API_CONNECTIVITY_FAILURE",
        "HEARTBEAT_TIMEOUT",
    }
)


def should_escalate(hazard_type: str, severity: str) -> bool:
    """Return True if the hazard warrants automatic severity escalation."""
    if hazard_type in _AUTO_ESCALATE_TYPES:
        return True
    if hazard_type in _ESCALATE_ON_HIGH and severity in {"HIGH", "CRITICAL"}:
        return True
    return False


def escalate_severity(current: str) -> str:
    """Return the next-higher severity level, capped at CRITICAL."""
    idx = _SEVERITY_ORDER.get(current, 1)
    return _SEVERITY_NAMES[min(idx + 1, len(_SEVERITY_NAMES) - 1)]
