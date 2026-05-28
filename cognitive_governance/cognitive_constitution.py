"""
cognitive_governance/cognitive_constitution.py
DIX VISION v42.2 — Cognitive Constitution

Encodes the P1 cognitive authority rules: what cognitive violations
BLOCK (gate) other governance layers, versus what merely generates
a warning for operator review.

The cognitive constitution is the highest-priority enforcement surface
in the development phase. It does NOT execute trades or modify parameters.
It gates: mutation proposals, learning updates, and (via escalation) mode
transitions.

BLOCKING rules (cognitive violations that halt a downstream operation):
  - CRITICAL epistemic drift → block new learning updates
  - Irreversible mutation detected → block mutation proposal
  - Hallucination loop depth >= 3 → block signal from propagating
  - Calibration drift CRITICAL → block strategy selection updates
  - Reward hacking detected → block reward-based parameter updates
  - Memory contamination CRITICAL → block that store from being read by learner

WARNING-only rules (logged, operator alerted, not blocked):
  - Epistemic drift WARNING
  - Learning external-signal ratio below threshold
  - Identity similarity below threshold
  - Synthetic feedback routing contamination (not CRITICAL)
  - Strategy lineage cycle detected (operator must review)

Enforcement is asymmetric: during development, cognitive integrity is the
PRIMARY safety constraint. Capital protection is subordinate.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from core.contracts.cognitive_governance import (
    CognitiveSeverity,
    CognitiveViolationKind,
)


class CognitiveGateKind(StrEnum):
    """Type of gate a cognitive violation can trigger."""
    BLOCK_MUTATION      = "BLOCK_MUTATION"
    BLOCK_LEARNING      = "BLOCK_LEARNING"
    BLOCK_SIGNAL        = "BLOCK_SIGNAL"
    BLOCK_STRATEGY_SEL  = "BLOCK_STRATEGY_SEL"
    WARN_OPERATOR       = "WARN_OPERATOR"
    ESCALATE_MODE       = "ESCALATE_MODE"


@dataclass(frozen=True, slots=True)
class GateDecision:
    """Result of applying the cognitive constitution to a proposed action."""
    action_kind: str           # "mutation" | "learning_update" | "signal" | etc.
    allowed: bool
    gate_kind: CognitiveGateKind | None
    violations: tuple[CognitiveViolationKind, ...]
    reason: str
    ts_ns: int


# Mapping: violation → gate kind (BLOCKING violations)
_BLOCKING_GATES: dict[CognitiveViolationKind, CognitiveGateKind] = {
    CognitiveViolationKind.EPISTEMIC_DRIFT_CRITICAL:  CognitiveGateKind.BLOCK_LEARNING,
    CognitiveViolationKind.MUTATION_IRREVERSIBLE:     CognitiveGateKind.BLOCK_MUTATION,
    CognitiveViolationKind.MUTATION_OUT_OF_BUDGET:    CognitiveGateKind.BLOCK_MUTATION,
    CognitiveViolationKind.HALLUCINATION_LOOP:        CognitiveGateKind.BLOCK_SIGNAL,
    CognitiveViolationKind.CALIBRATION_DRIFT:         CognitiveGateKind.BLOCK_STRATEGY_SEL,
    CognitiveViolationKind.REWARD_HACKING:            CognitiveGateKind.BLOCK_LEARNING,
    CognitiveViolationKind.MEMORY_CONTAMINATION:      CognitiveGateKind.BLOCK_LEARNING,
    CognitiveViolationKind.LINEAGE_CYCLE:             CognitiveGateKind.BLOCK_MUTATION,
    CognitiveViolationKind.LINEAGE_GAP:               CognitiveGateKind.BLOCK_MUTATION,
    CognitiveViolationKind.SELF_REFERENTIAL_REWARD:   CognitiveGateKind.BLOCK_LEARNING,
    CognitiveViolationKind.SYNTHETIC_FEEDBACK:        CognitiveGateKind.BLOCK_LEARNING,
}

# Warning-only violations (not blocking)
_WARNING_VIOLATIONS: frozenset[CognitiveViolationKind] = frozenset({
    CognitiveViolationKind.EPISTEMIC_DRIFT_WARNING,
    CognitiveViolationKind.LEARNING_NOT_GROUNDED,
    CognitiveViolationKind.IDENTITY_INSTABILITY,
    CognitiveViolationKind.CAUSAL_GHOST,
    CognitiveViolationKind.CAUSAL_DOMAIN_LEAK,
    CognitiveViolationKind.OVERCONFIDENCE,
    CognitiveViolationKind.MAGICAL_BELIEF_JUMP,
    CognitiveViolationKind.EMBEDDING_COLLAPSE,
})


class CognitiveConstitution:
    """
    P1 enforcement layer for cognitive integrity.

    Thread-safe. Evaluates whether a proposed action is allowed given
    the current set of active cognitive violations.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Active violations currently in effect
        self._active_violations: set[CognitiveViolationKind] = set()
        self._gate_log: list[GateDecision] = []
        self._max_log = 500

    def record_violation(self, violation: CognitiveViolationKind) -> None:
        with self._lock:
            self._active_violations.add(violation)

    def clear_violation(self, violation: CognitiveViolationKind) -> None:
        with self._lock:
            self._active_violations.discard(violation)

    def clear_all_violations(self) -> None:
        with self._lock:
            self._active_violations.clear()

    def active_violations(self) -> frozenset[CognitiveViolationKind]:
        with self._lock:
            return frozenset(self._active_violations)

    def gate(
        self,
        action_kind: str,
        ts_ns: int,
        override_violations: tuple[CognitiveViolationKind, ...] | None = None,
    ) -> GateDecision:
        """
        Evaluate whether action_kind is permitted under current violations.

        Args:
            action_kind:  "mutation" | "learning_update" | "signal" |
                          "strategy_selection" | "execution"
            ts_ns:        Current timestamp.
            override_violations: If provided, evaluate against these instead
                                 of the currently active set (for testing).

        Returns:
            GateDecision with allowed=False if any BLOCKING violation applies.
        """
        with self._lock:
            violations = frozenset(override_violations) if override_violations is not None \
                else frozenset(self._active_violations)

        blocking_viols: list[CognitiveViolationKind] = []
        first_gate: CognitiveGateKind | None = None

        for v in violations:
            gate_kind = _BLOCKING_GATES.get(v)
            if gate_kind is None:
                continue
            # Check if this gate applies to the requested action_kind
            if self._gate_applies(action_kind, gate_kind):
                blocking_viols.append(v)
                if first_gate is None:
                    first_gate = gate_kind

        allowed = len(blocking_viols) == 0
        reason_parts: list[str] = []
        if not allowed:
            reason_parts = [f"{v.value}" for v in blocking_viols]
        reason = f"blocked_by=[{', '.join(reason_parts)}]" if reason_parts else "ok"

        decision = GateDecision(
            action_kind=action_kind,
            allowed=allowed,
            gate_kind=first_gate,
            violations=tuple(blocking_viols),
            reason=reason,
            ts_ns=ts_ns,
        )

        with self._lock:
            self._gate_log.append(decision)
            if len(self._gate_log) > self._max_log:
                self._gate_log = self._gate_log[-self._max_log:]

        return decision

    def _gate_applies(self, action_kind: str, gate_kind: CognitiveGateKind) -> bool:
        """Map gate_kind to whether it applies to action_kind."""
        if gate_kind == CognitiveGateKind.BLOCK_MUTATION:
            return action_kind in ("mutation", "parameter_update", "evolution")
        if gate_kind == CognitiveGateKind.BLOCK_LEARNING:
            return action_kind in ("learning_update", "reward_update", "distillation")
        if gate_kind == CognitiveGateKind.BLOCK_SIGNAL:
            return action_kind in ("signal", "intent", "execution")
        if gate_kind == CognitiveGateKind.BLOCK_STRATEGY_SEL:
            return action_kind in ("strategy_selection", "archetype_promotion")
        return False

    def gate_mutation(self, ts_ns: int) -> GateDecision:
        return self.gate("mutation", ts_ns)

    def gate_learning_update(self, ts_ns: int) -> GateDecision:
        return self.gate("learning_update", ts_ns)

    def gate_signal(self, ts_ns: int) -> GateDecision:
        return self.gate("signal", ts_ns)

    def gate_strategy_selection(self, ts_ns: int) -> GateDecision:
        return self.gate("strategy_selection", ts_ns)

    def recent_blocks(self, n: int = 20) -> list[GateDecision]:
        with self._lock:
            blocked = [d for d in self._gate_log if not d.allowed]
        return blocked[-n:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active_violations": [v.value for v in self._active_violations],
                "gate_log_size": len(self._gate_log),
                "recent_blocks": len([d for d in self._gate_log if not d.allowed]),
            }


# Singleton factory
_instance: CognitiveConstitution | None = None
_lock = threading.Lock()


def get_cognitive_constitution() -> CognitiveConstitution:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = CognitiveConstitution()
    return _instance


__all__ = [
    "CognitiveConstitution",
    "CognitiveGateKind",
    "GateDecision",
    "get_cognitive_constitution",
]
