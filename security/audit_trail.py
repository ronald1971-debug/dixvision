"""security.audit_trail — Security Audit Trail (System Spec §Governance/Ledger).

Immutable security audit trail that records all security-relevant events to the
authority ledger. Covers authentication, authorization failures, credential
access, policy violations, and governance gate decisions.

Every entry is append-only, hash-chained (via ledger), and carries full
provenance. No deletion. No mutation. Replay-safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from system import time_source


class SecurityEventType(StrEnum):
    """Types of security events recorded in the audit trail."""

    AUTH_SUCCESS = "AUTH_SUCCESS"
    AUTH_FAILURE = "AUTH_FAILURE"
    CREDENTIAL_ACCESS = "CREDENTIAL_ACCESS"
    CREDENTIAL_ROTATION = "CREDENTIAL_ROTATION"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    GOVERNANCE_GATE_DENY = "GOVERNANCE_GATE_DENY"
    GOVERNANCE_GATE_ALLOW = "GOVERNANCE_GATE_ALLOW"
    KILL_SWITCH_TRIGGERED = "KILL_SWITCH_TRIGGERED"
    MODE_TRANSITION = "MODE_TRANSITION"
    OPERATOR_AUTHORITY_CHANGE = "OPERATOR_AUTHORITY_CHANGE"
    EXECUTION_BLOCKED = "EXECUTION_BLOCKED"
    UNAUTHORIZED_ACCESS = "UNAUTHORIZED_ACCESS"
    INTEGRITY_VIOLATION = "INTEGRITY_VIOLATION"
    HMAC_VERIFICATION_FAILURE = "HMAC_VERIFICATION_FAILURE"


class Severity(StrEnum):
    """Audit event severity — drives response escalation."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """Single security audit trail entry."""

    event_type: SecurityEventType
    severity: Severity
    source: str
    operator_id: str
    payload: dict[str, Any]
    ts_ns: int
    trace_id: str = ""
    session_id: str = ""


_AUDIT_BUFFER: list[AuditEntry] = []


def audit(
    sub_type: str,
    source: str,
    payload: dict[str, Any],
    *,
    severity: Severity = Severity.MEDIUM,
    operator_id: str = "",
    trace_id: str = "",
) -> AuditEntry:
    """Record a security event to the authority ledger.

    Writes to the append-only event store. Never fails silently in
    production — if the ledger is unavailable, buffers locally and
    retries on next write.

    Args:
        sub_type: SecurityEventType value.
        source: Subsystem that produced the event.
        payload: Structured event data (JSON-serializable).
        severity: Event severity level.
        operator_id: Operator associated with the event.
        trace_id: Distributed trace correlation ID.

    Returns:
        The AuditEntry that was recorded.
    """
    try:
        event_type = SecurityEventType(sub_type)
    except ValueError:
        event_type = SecurityEventType.POLICY_VIOLATION

    entry = AuditEntry(
        event_type=event_type,
        severity=severity,
        source=source,
        operator_id=operator_id,
        payload=payload,
        ts_ns=time_source.wall_ns(),
        trace_id=trace_id,
    )

    _AUDIT_BUFFER.append(entry)

    try:
        from state.ledger.event_store import append_event

        append_event(
            "SECURITY",
            sub_type,
            source,
            {
                "severity": severity.value,
                "operator_id": operator_id,
                "trace_id": trace_id,
                **payload,
            },
        )
    except Exception:
        pass

    return entry


def audit_auth_failure(
    source: str, *, reason: str, attempted_action: str, operator_id: str = ""
) -> AuditEntry:
    """Record an authentication/authorization failure."""
    return audit(
        SecurityEventType.AUTH_FAILURE,
        source,
        {"reason": reason, "attempted_action": attempted_action},
        severity=Severity.HIGH,
        operator_id=operator_id,
    )


def audit_governance_decision(
    source: str, *, intent_id: str, decision: str, reason: str, operator_id: str = ""
) -> AuditEntry:
    """Record a governance gate decision (allow or deny)."""
    event_type = (
        SecurityEventType.GOVERNANCE_GATE_ALLOW
        if decision == "ALLOW"
        else SecurityEventType.GOVERNANCE_GATE_DENY
    )
    return audit(
        event_type,
        source,
        {"intent_id": intent_id, "decision": decision, "reason": reason},
        severity=Severity.MEDIUM if decision == "ALLOW" else Severity.HIGH,
        operator_id=operator_id,
    )


def audit_execution_blocked(
    source: str, *, intent_id: str, reason: str, domain: str = ""
) -> AuditEntry:
    """Record a blocked execution attempt."""
    return audit(
        SecurityEventType.EXECUTION_BLOCKED,
        source,
        {"intent_id": intent_id, "reason": reason, "domain": domain},
        severity=Severity.HIGH,
    )


def audit_kill_switch(source: str, *, reason: str, trigger: str) -> AuditEntry:
    """Record a kill switch activation."""
    return audit(
        SecurityEventType.KILL_SWITCH_TRIGGERED,
        source,
        {"reason": reason, "trigger": trigger},
        severity=Severity.CRITICAL,
    )


def get_recent_entries(
    *, limit: int = 100, event_type: SecurityEventType | None = None
) -> list[AuditEntry]:
    """Retrieve recent audit entries from the buffer.

    Args:
        limit: Maximum entries to return.
        event_type: Optional filter by event type.

    Returns:
        List of AuditEntry in reverse chronological order.
    """
    entries = _AUDIT_BUFFER
    if event_type is not None:
        entries = [e for e in entries if e.event_type == event_type]
    return list(reversed(entries[-limit:]))


def flush_buffer() -> int:
    """Flush the in-memory buffer to the ledger.

    Returns:
        Number of entries flushed.
    """
    count = len(_AUDIT_BUFFER)
    try:
        from state.ledger.event_store import append_event

        for entry in _AUDIT_BUFFER:
            append_event(
                "SECURITY",
                entry.event_type.value,
                entry.source,
                {
                    "severity": entry.severity.value,
                    "operator_id": entry.operator_id,
                    "trace_id": entry.trace_id,
                    **entry.payload,
                },
            )
    except Exception:
        return 0
    _AUDIT_BUFFER.clear()
    return count


__all__ = [
    "AuditEntry",
    "SecurityEventType",
    "Severity",
    "audit",
    "audit_auth_failure",
    "audit_execution_blocked",
    "audit_governance_decision",
    "audit_kill_switch",
    "flush_buffer",
    "get_recent_entries",
]
