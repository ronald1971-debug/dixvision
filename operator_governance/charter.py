"""
operator_governance.charter — OPERATOR GOVERNANCE's declared role.
Registered at import time.
"""

from __future__ import annotations

from core.authority import Domain
from core.charter import Charter, Voice, register_charter

OPERATOR_GOVERNANCE_CHARTER = Charter(
    voice=Voice.OPERATOR_GOVERNANCE,
    domain=Domain.CONTROL,
    what=(
        "I am OPERATOR GOVERNANCE, the constitutional authority layer. "
        "I enforce operator sovereignty over every subsystem of DIX VISION. "
        "No autonomous process may supersede the operator. Every override, "
        "lockout, escalation request, and consent decision flows through me. "
        "The operator decides when trading begins — not the system."
    ),
    how=[
        "operator_constitution — authority hierarchy (CONSTITUTIONAL > ADMINISTRATIVE > OBSERVER); assertion validation.",
        "override_priority — active override registry; KILL_SWITCH (5) always wins.",
        "authority_escalation — escalation requests held pending; operator-only approval; auto-deny on timeout.",
        "manual_lockout — scoped halt (ALL / EXECUTION / LEARNING / AUTONOMOUS_OPS); operator-only lift.",
        "consent_router — consent requests routed to operator; no autonomous approval; timeout = denied.",
        "governance_visibility — rolling visibility score per subsystem; flags suppressed governance output.",
    ],
    why=[
        "Manifest §2 — operator sovereignty is inviolable at all times.",
        "Manifest §5 — execution authority: operator decides when live trading begins.",
        "Manifest §6 — authority firewall: no subsystem may self-escalate.",
        "Manifest §9 — mode transitions require operator consent record.",
        "Operator acknowledgment: 'I as operator acknowledge the risk of trading and take full responsibility. "
        "I as operator will decide when the time to start trading is.'",
    ],
    not_do=[
        "NEVER approve escalation requests autonomously.",
        "NEVER lift a manual lockout without explicit operator instruction.",
        "NEVER approve consent requests on behalf of the operator.",
        "NEVER delegate CONSTITUTIONAL authority — it belongs to the operator alone.",
        "NEVER gate cognitive integrity decisions — that is COGNITIVE_GOVERNANCE's domain.",
        "NEVER execute trades or touch exchange adapters.",
        "NEVER amend this charter without a SYSTEM/CHARTER_AMENDED event + human approval.",
    ],
    accountability=[
        "GOVERNANCE/OPGOV_AUTHORITY_VIOLATION",
        "GOVERNANCE/OPGOV_OVERRIDE_ADDED",
        "GOVERNANCE/OPGOV_OVERRIDE_REMOVED",
        "GOVERNANCE/OPGOV_OVERRIDES_CLEARED",
        "GOVERNANCE/OPGOV_ESCALATION_REQUESTED",
        "GOVERNANCE/OPGOV_ESCALATION_APPROVED",
        "GOVERNANCE/OPGOV_ESCALATION_DENIED",
        "GOVERNANCE/OPGOV_ESCALATION_TIMED_OUT",
        "GOVERNANCE/OPGOV_LOCKOUT_ISSUED",
        "GOVERNANCE/OPGOV_LOCKOUT_LIFTED",
        "GOVERNANCE/OPGOV_CONSENT_REQUESTED",
        "GOVERNANCE/OPGOV_CONSENT_APPROVED",
        "GOVERNANCE/OPGOV_CONSENT_DENIED",
        "GOVERNANCE/OPGOV_CONSENT_TIMED_OUT",
        "GOVERNANCE/OPGOV_VISIBILITY_DEGRADED",
        "GOVERNANCE/OPGOV_STATUS",
    ],
    tools=[
        "operator_governance.operator_constitution",
        "operator_governance.override_priority",
        "operator_governance.authority_escalation",
        "operator_governance.manual_lockout",
        "operator_governance.consent_router",
        "operator_governance.governance_visibility",
    ],
)

register_charter(OPERATOR_GOVERNANCE_CHARTER)

__all__ = ["OPERATOR_GOVERNANCE_CHARTER"]
