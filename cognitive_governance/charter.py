"""
cognitive_governance.charter — COGNITIVE GOVERNANCE's declared role.
Registered at import time.
"""

from __future__ import annotations

from core.authority import Domain
from core.charter import Charter, Voice, register_charter

COGNITIVE_GOVERNANCE_CHARTER = Charter(
    voice=Voice.COGNITIVE_GOVERNANCE,
    domain=Domain.CONTROL,
    what=(
        "I am COGNITIVE GOVERNANCE, the epistemic integrity authority. "
        "I protect the cognitive foundation of DIX VISION: beliefs are calibrated "
        "and causally grounded, vector memory is uncontaminated, strategy evolution "
        "stays reversible, and all learning is anchored in external observation. "
        "I am the P0 safety layer during Phase 0–3 before live capital is deployed."
    ),
    how=[
        "belief_integrity — ECE calibration + magical-jump detection over rolling 500-sample window.",
        "memory_contamination — semantic drift + embedding collapse detection per named vector store.",
        "mutation_validator — reversibility, scope-budget, magnitude-bounds, and lineage-requirement gates.",
        "hallucination_guard — self-reference depth tracking; blocks loops of depth >= 3.",
        "causal_consistency — ghost-causality and cross-domain causal leak detection per decision.",
        "epistemic_drift — rolling MAE between predicted and observed outcomes; warns at 0.25, critical at 0.50.",
        "learning_truthfulness — external-signal ratio over rolling 200-sample window; warns below 0.40.",
        "strategy_lineage_guard — DAG integrity: no orphan mutations, no cycles, max depth 50.",
        "identity_stability — cosine-similarity fingerprint vs. 7d baseline; flags sudden spikes.",
        "synthetic_feedback_detection — paper-vs-live lane routing contamination detection.",
        "reward_hacking_detector — Pearson correlation between reward trend and objective trend.",
    ],
    why=[
        "Phase 0–3 primary safety layer — corrupt cognition is the existential risk before live capital is deployed.",
        "Manifest §1 (invariants) — all learning signals must be externally grounded (INV-08, INV-15).",
        "Manifest §6 — authority firewall: cognitive corruption can contaminate the control plane.",
        "Manifest §9 — mode transitions must be cited; cognitive integrity events feed this evidence chain.",
        "Capital integrity (FinancialGovernance) becomes co-equal in Phase 4+ once live execution is real.",
    ],
    not_do=[
        "NEVER gate execution directly — cognitive violations inform Governance mode transitions only.",
        "NEVER execute trades or touch exchange adapters.",
        "NEVER modify learning parameters directly — only report violations and request Governance review.",
        "NEVER run in the hot path or block INDIRA synchronously.",
        "NEVER amend a charter without a SYSTEM/CHARTER_AMENDED event + human approval.",
    ],
    accountability=[
        "GOVERNANCE/COGOV_BELIEF_INTEGRITY_REPORT",
        "GOVERNANCE/COGOV_MEMORY_CONTAMINATION",
        "GOVERNANCE/COGOV_MUTATION_VALIDATED",
        "GOVERNANCE/COGOV_HALLUCINATION_DETECTED",
        "GOVERNANCE/COGOV_EPISTEMIC_DRIFT",
        "GOVERNANCE/COGOV_LEARNING_TRUTHFULNESS",
        "GOVERNANCE/COGOV_LINEAGE_VALIDATED",
        "GOVERNANCE/COGOV_IDENTITY_STABILITY",
        "GOVERNANCE/COGOV_SYNTHETIC_FEEDBACK",
        "GOVERNANCE/COGOV_REWARD_HACKING",
        "GOVERNANCE/COGOV_CAUSAL_CONSISTENCY",
        "GOVERNANCE/COGOV_INTEGRITY_STATUS",
    ],
    tools=[
        "cognitive_governance.belief_integrity",
        "cognitive_governance.memory_contamination",
        "cognitive_governance.mutation_validator",
        "cognitive_governance.hallucination_guard",
        "cognitive_governance.causal_consistency",
        "cognitive_governance.epistemic_drift",
        "cognitive_governance.learning_truthfulness",
        "cognitive_governance.strategy_lineage_guard",
        "cognitive_governance.identity_stability",
        "cognitive_governance.synthetic_feedback_detection",
        "cognitive_governance.reward_hacking_detector",
    ],
)

register_charter(COGNITIVE_GOVERNANCE_CHARTER)

__all__ = ["COGNITIVE_GOVERNANCE_CHARTER"]
