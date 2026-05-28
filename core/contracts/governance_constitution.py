"""
core/contracts/governance_constitution.py
DIX VISION v42.2 — Governance Constitution Contracts

Encodes the DIXVISION Executive Constitution as frozen, typed contracts.
These are the inviolable rules that ALL governance layers enforce and ALL
subsystems must observe. No layer may supersede these rules.

DIXVISION is NOT merely a trading system. It is:
  - A cognitive operating system
  - A trader intelligence ecosystem
  - A self-evolving market cognition engine
  - An epistemic learning framework
  - An eventual live execution environment

Therefore governance must protect ALL foundational layers simultaneously,
prioritised correctly by phase.

This module contains NO callables, NO IO, NO mutable state.
It is imported at the very root of the governance stack (INV-08, INV-15).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


# ---------------------------------------------------------------------------
# Priority enumeration (dev and live phases)
# ---------------------------------------------------------------------------

class GovernancePriority(StrEnum):
    """Ordinal priority identifier for a governance layer."""
    P1_COGNITIVE  = "P1_COGNITIVE"    # Always P1 — protects cognition
    P2_OPERATOR   = "P2_OPERATOR"     # Dev P2 / Live P3 — constitutional authority
    P3_SYSTEM     = "P3_SYSTEM"       # Dev P3 / Live P4 — runtime integrity
    P4_CAPITAL    = "P4_CAPITAL"      # Dev P4 / Live P2 — financial protection


class DeploymentPhase(StrEnum):
    """System deployment phase that determines priority ordering."""
    DEVELOPMENT = "DEVELOPMENT"   # Phase 0–3: cognitive build-out
    LIVE        = "LIVE"          # Phase 4+:  live capital deployed


# Priority stacks: (layer → ordinal rank; lower = higher priority)
DEV_PRIORITY_STACK: dict[GovernancePriority, int] = {
    GovernancePriority.P1_COGNITIVE: 1,
    GovernancePriority.P2_OPERATOR:  2,
    GovernancePriority.P3_SYSTEM:    3,
    GovernancePriority.P4_CAPITAL:   4,
}

LIVE_PRIORITY_STACK: dict[GovernancePriority, int] = {
    GovernancePriority.P1_COGNITIVE: 1,
    GovernancePriority.P4_CAPITAL:   2,   # capital becomes co-equal in live
    GovernancePriority.P2_OPERATOR:  3,
    GovernancePriority.P3_SYSTEM:    4,
}


def priority_stack(phase: DeploymentPhase) -> dict[GovernancePriority, int]:
    return DEV_PRIORITY_STACK if phase == DeploymentPhase.DEVELOPMENT else LIVE_PRIORITY_STACK


# ---------------------------------------------------------------------------
# Constitutional directives (codified immutable rules)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ConstitutionalDirective:
    """One inviolable rule in the DIXVISION governance constitution."""
    directive_id: str
    title: str
    text: str
    enforced_by: str      # module path of the enforcing guard
    blocking: bool        # True = violations BLOCK execution; False = warn only


# The four primary directives — ordered by priority
COGNITIVE_INTEGRITY_DIRECTIVE = ConstitutionalDirective(
    directive_id="CONST-01",
    title="Cognitive Integrity",
    text=(
        "The system shall prioritise truthful cognition over profitable cognition. "
        "No subsystem may corrupt learning lineage, fabricate confidence, reinforce "
        "hallucinated alpha, mutate beyond traceability, poison memory structures, "
        "create irreversible self-modifications, or bypass epistemic validation. "
        "This is the PRIMARY directive during all development phases."
    ),
    enforced_by="cognitive_governance.engine",
    blocking=True,
)

OPERATOR_SOVEREIGNTY_DIRECTIVE = ConstitutionalDirective(
    directive_id="CONST-02",
    title="Operator Sovereignty",
    text=(
        "The operator retains supreme constitutional authority. "
        "No autonomous process may remove operator visibility, bypass explicit operator "
        "restrictions, escalate autonomy without governance approval, or suppress operator "
        "intervention capability. CONSTITUTIONAL authority cannot be delegated to any "
        "autonomous subsystem. The operator decides when to start trading."
    ),
    enforced_by="operator_governance.engine",
    blocking=True,
)

SYSTEM_INTEGRITY_DIRECTIVE = ConstitutionalDirective(
    directive_id="CONST-03",
    title="System Integrity",
    text=(
        "All system evolution must remain deterministic, auditable, replayable, "
        "contract-valid, and reversibly traceable. Architectural convergence is mandatory: "
        "every subsystem must consume real contracts, produce measurable outputs, integrate "
        "into runtime, emit governance artifacts, support replay, support observability, "
        "support mutation lineage, and support operator visibility. "
        "Speculative divergence without runtime integration is prohibited."
    ),
    enforced_by="system_governance.engine",
    blocking=True,
)

CAPITAL_INTEGRITY_DIRECTIVE = ConstitutionalDirective(
    directive_id="CONST-04",
    title="Capital Integrity",
    text=(
        "Capital protection mechanisms shall activate proportionally to the system's "
        "live financial authority level. Before live deployment: focus on realism "
        "validation and execution simulation integrity. During live deployment: risk "
        "governance becomes fully active. Capital protection becomes co-equal with "
        "cognitive protection once real capital is at risk."
    ),
    enforced_by="financial_governance.engine",
    blocking=True,
)

ALL_DIRECTIVES: tuple[ConstitutionalDirective, ...] = (
    COGNITIVE_INTEGRITY_DIRECTIVE,
    OPERATOR_SOVEREIGNTY_DIRECTIVE,
    SYSTEM_INTEGRITY_DIRECTIVE,
    CAPITAL_INTEGRITY_DIRECTIVE,
)


# ---------------------------------------------------------------------------
# Architecture identity declaration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ArchitectureIdentity:
    """The true identity of the DIXVISION system (not merely a trading bot)."""
    primary_identity: str
    manifestations: tuple[str, ...]
    governance_target: str
    development_priority: str
    live_priority: str


DIXVISION_IDENTITY = ArchitectureIdentity(
    primary_identity="Adaptive Cognitive Market Intelligence Operating System",
    manifestations=(
        "Cognitive operating system",
        "Trader intelligence ecosystem",
        "Self-evolving market cognition engine",
        "Epistemic learning framework",
        "Live execution environment (future manifestation)",
    ),
    governance_target=(
        "Preserve cognitive integrity, operator sovereignty, system integrity, "
        "and capital integrity — simultaneously, in priority order by phase."
    ),
    development_priority=(
        "P1 Cognitive → P2 Operator → P3 System → P4 Capital"
    ),
    live_priority=(
        "P1 Cognitive → P2 Capital → P3 Operator → P4 System"
    ),
)


# ---------------------------------------------------------------------------
# Governance status snapshot
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ConstitutionalStatus:
    """Snapshot of constitutional compliance across all four governance layers."""
    ts_ns: int
    phase: DeploymentPhase
    cognitive_integrity_ok: bool
    operator_sovereignty_ok: bool
    system_integrity_ok: bool
    capital_integrity_ok: bool
    overall_compliant: bool
    blocking_violations: tuple[str, ...]
    detail: str = ""

    @property
    def governance_healthy(self) -> bool:
        return self.overall_compliant


__all__ = [
    # Enums
    "DeploymentPhase",
    "GovernancePriority",
    # Priority stacks
    "DEV_PRIORITY_STACK",
    "LIVE_PRIORITY_STACK",
    "ALL_DIRECTIVES",
    "priority_stack",
    # Directives
    "CAPITAL_INTEGRITY_DIRECTIVE",
    "COGNITIVE_INTEGRITY_DIRECTIVE",
    "ConstitutionalDirective",
    "OPERATOR_SOVEREIGNTY_DIRECTIVE",
    "SYSTEM_INTEGRITY_DIRECTIVE",
    # Identity
    "ArchitectureIdentity",
    "DIXVISION_IDENTITY",
    # Status
    "ConstitutionalStatus",
]
