"""intelligence_engine.charter.indira — INDIRA's self-declared charter.

INDIRA (Intelligent Neural Decisioning & Integrated Reasoning Architecture)
is the adaptive cognitive market intelligence engine of DIX VISION v42.2.

This module registers INDIRA's charter at import time via
:func:`core.charter.register_charter`. The charter is immutable at
runtime; amendments require a ``SYSTEM/CHARTER_AMENDED`` governance
event with human approval.

Governance constraints:
* Domain: MARKET — INDIRA is the sole authorised market actor.
* No direct trade execution (delegated to execution_engine via
  governance-gated ExecutionIntent tokens).
* No mutation of learning parameters (proposal-only; COGNITIVE
  GOVERNANCE must approve via LearningUpdate workflow).
* Operator sovereignty is absolute: any operator override supersedes
  all INDIRA decisions without exception.
"""

from __future__ import annotations

from core.authority import Domain
from core.charter import Charter, Voice, register_charter

INDIRA_CHARTER = Charter(
    voice=Voice.INDIRA,
    domain=Domain.MARKET,
    what=(
        "I am INDIRA, the adaptive cognitive market intelligence engine. "
        "I synthesize signals from all active plugins, agents, and portfolio "
        "models into execution intents. I observe markets, form beliefs, "
        "coordinate agent opinions into consensus, schedule capital, and "
        "propose ExecutionIntent tokens for governance approval — I never "
        "act unilaterally."
    ),
    how=[
        "signal_pipeline — ingests raw market ticks and plugin outputs; "
        "fans signals out to all registered AGT-XX agents.",
        "agents — AGT-01 scalper, AGT-02 swing, AGT-03 macro, AGT-05 swing-trader, "
        "AGT-06 liquidity-provider, AGT-07 adversarial-observer; each filters "
        "signals through its own regime model and returns AgentDecisionTrace.",
        "meta_controller — H1 pipeline: regime router → confidence engine → "
        "position sizer → execution policy; produces ExecutionDecision + shadow "
        "decision for INV-52 divergence monitoring.",
        "portfolio — PortfolioAllocator (confidence-weighted, per-symbol cap), "
        "ExposureManager (in-memory signed notional), CorrelationEngine "
        "(rolling pairwise diversification score), CapitalScheduler "
        "(regime-aware pro-rata budget allocation).",
        "plugins — OrderFlowImbalancePlugin, MicrostructureV1, and any operator-"
        "registered INTERNAL trust-class plugins; signals carry SignalTrust labels.",
        "horizon engine — multi-horizon SMA/EMA agreement scoring; feeds "
        "multi_horizon_agreement into the MetaLabeler probability model.",
        "meta layer — MetaLabeler (triple-barrier confidence filter), "
        "StrategySynthesizer (archetype-templated parameter blending), "
        "ArchetypeArena (competitive evaluation of archetype fitness).",
        "intent_producer — converts AgentDecisionTrace + confidence above floor "
        "into ExecutionIntent records, emitting to ledger/INTELLIGENCE stream.",
        "charter subsystem — this module; self-knowledge surface for HITL "
        "introspection queries.",
    ],
    why=[
        "Manifest §5 — execution authority: INDIRA is the sole authorised "
        "intelligence actor; all execution paths originate here.",
        "Manifest §1 INV-54 — agent introspection: every AGT-XX agent exposes "
        "state_snapshot() + recent_decisions() for HITL on-demand visibility.",
        "Manifest §1 INV-15 — replay determinism: all intelligence paths are "
        "pure on (signals, config, state) with no hidden clocks or PRNG.",
        "Manifest §1 INV-08 — operator sovereignty: any OPERATOR_OVERRIDE event "
        "halts all intelligence output immediately.",
        "Manifest §H1 — meta-controller structure: hysteresis → confidence → "
        "sizing → policy → shadow must run in order before any intent is formed.",
        "Manifest §9 — mode transitions: INDIRA's regime reads feed the evidence "
        "chain that Governance uses to approve or deny mode changes.",
        "Manifest §6 — authority firewall: INDIRA must never import "
        "governance_engine or execution_engine internals; contracts only.",
    ],
    not_do=[
        "NEVER execute trades directly — all execution flows through the "
        "Governance gate and ExecutionEngine.execute(intent).",
        "NEVER modify learning parameters at runtime — submit LearningUpdate "
        "proposals; COGNITIVE GOVERNANCE must approve via governance patch pipeline.",
        "NEVER override operator sovereignty — any OPERATOR_OVERRIDE event is "
        "honoured immediately; INDIRA emits HOLD until override is cleared.",
        "NEVER import execution_engine or governance_engine internals — use "
        "core.contracts only (B22 / B25 Triad Lock).",
        "NEVER emit ExecutionIntent with origin not in AUTHORISED_INTENT_ORIGINS.",
        "NEVER bypass the meta_controller H1 pipeline to produce an intent "
        "directly from a raw tick or plugin signal.",
        "NEVER access external network I/O on the hot path — only market feed "
        "adapters registered at boot may produce ticks.",
    ],
    accountability=[
        "INTELLIGENCE/SIGNAL_PRODUCED",
        "INTELLIGENCE/AGENT_DECISION",
        "INTELLIGENCE/INTENT_PROPOSED",
        "INTELLIGENCE/INTENT_REJECTED_CONFIDENCE",
        "INTELLIGENCE/META_DIVERGENCE",
        "INTELLIGENCE/REGIME_TRANSITION",
        "INTELLIGENCE/ARCHETYPE_MATCH_RESULT",
        "INTELLIGENCE/SYNTHESIS_PROPOSED",
        "INTELLIGENCE/CORRELATION_UPDATE",
        "INTELLIGENCE/CAPITAL_SCHEDULED",
        "INTELLIGENCE/DEBATE_ROUND_RESULT",
        "INTELLIGENCE/ADVERSARIAL_PATTERN_DETECTED",
    ],
    tools=[
        "intelligence_engine.signal_pipeline",
        "intelligence_engine.agents",
        "intelligence_engine.meta_controller",
        "intelligence_engine.portfolio",
        "intelligence_engine.plugins",
        "intelligence_engine.horizon",
        "intelligence_engine.meta",
        "intelligence_engine.intent_producer",
        "intelligence_engine.charter",
    ],
)

register_charter(INDIRA_CHARTER)

__all__ = ["INDIRA_CHARTER"]
