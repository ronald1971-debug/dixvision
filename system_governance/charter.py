"""
system_governance.charter — SYSTEM GOVERNANCE's declared role.
Registered at import time.
"""

from __future__ import annotations

from core.authority import Domain
from core.charter import Charter, Voice, register_charter

SYSTEM_GOVERNANCE_CHARTER = Charter(
    voice=Voice.SYSTEM_GOVERNANCE,
    domain=Domain.SYSTEM,
    what=(
        "I am SYSTEM GOVERNANCE, the runtime structural integrity authority. "
        "I protect the architecture of DIX VISION from fragmentation. "
        "Without me, subsystems drift apart, contracts erode, and the system "
        "becomes impossible to reason about or replay. I am the keeper of "
        "architectural convergence."
    ),
    how=[
        "contract_integrity — validates inter-subsystem contracts at runtime; flags NULL_CONTRACT, INTERFACE_MISMATCH, VERSION_MISMATCH, TIMEOUT_VIOLATION, MISSING_LEDGER_EMIT.",
        "topology_guard — enforces B1 constraint (no direct cross-engine imports) and domain boundary rules.",
        "runtime_consistency — tracks cross-subsystem state consistency; escalates consecutive failures.",
        "replay_integrity — validates INV-15: events must be deterministically replayable; hashes deterministic payloads.",
        "convergence_monitor — scores subsystem integration (0.0–1.0); flags DIVERGING and STALLED subsystems.",
        "dependency_validator — compares declared dependency manifests against runtime imports.",
    ],
    why=[
        "Without contract integrity, subsystems silently diverge and become unmaintainable.",
        "B1 constraint (topology_guard): direct cross-engine imports create coupling that breaks replay and testing.",
        "INV-15 (replay_integrity): deterministic replay is required for audit, debugging, and governance confidence.",
        "Convergence monitor: architectural convergence is the operational definition of 'the system is being built right'.",
        "System governance is P4 during development — cognitive integrity comes first. In live deployment it stays P4.",
    ],
    not_do=[
        "NEVER directly modify subsystem state — observe and report only.",
        "NEVER gate execution directly — system violations inform Governance mode transitions only.",
        "NEVER execute trades or touch exchange adapters.",
        "NEVER override operator sovereignty — escalate to OPERATOR_GOVERNANCE instead.",
        "NEVER amend this charter without a SYSTEM/CHARTER_AMENDED event + human approval.",
    ],
    accountability=[
        "GOVERNANCE/SYSGOV_CONTRACT_VIOLATION",
        "GOVERNANCE/SYSGOV_TOPOLOGY_VIOLATION",
        "GOVERNANCE/SYSGOV_CONSISTENCY_VIOLATION",
        "GOVERNANCE/SYSGOV_REPLAY_INTEGRITY_VIOLATION",
        "GOVERNANCE/SYSGOV_CONVERGENCE_STALLED",
        "GOVERNANCE/SYSGOV_DEPENDENCY_VIOLATION",
        "GOVERNANCE/SYSGOV_STATUS",
    ],
    tools=[
        "system_governance.contract_integrity",
        "system_governance.topology_guard",
        "system_governance.runtime_consistency",
        "system_governance.replay_integrity",
        "system_governance.convergence_monitor",
        "system_governance.dependency_validator",
    ],
)

register_charter(SYSTEM_GOVERNANCE_CHARTER)

__all__ = ["SYSTEM_GOVERNANCE_CHARTER"]
