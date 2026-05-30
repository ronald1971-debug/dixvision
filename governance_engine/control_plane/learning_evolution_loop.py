"""Learning↔Evolution loop state machine (BUILD-DIRECTIVE §10).

Explicit FSM governing mutation classes:

  Class A — Internal adaptive state (auto-applied during build-out)
    Examples: confidence calibration, reward shape, memory writes
    Gate: Learning != OFF

  Class B — Execution-influencing parameters (paper-scoped during build-out)
    Examples: position sizing, threshold tuning, strategy weights
    Gate: Practice == ON (routed to paper only during build-out)

  Class C — Operator-only controls (always require explicit operator action)
    Examples: live enable, safeguard disable, authority changes
    Gate: Operator dashboard action + ledger audit row

The state machine is:
  IDLE → COMPUTING → VALIDATING → APPLYING/QUEUED → IDLE
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MutationClass(StrEnum):
    """Classification of parameter mutations."""

    CLASS_A = "CLASS_A"
    CLASS_B = "CLASS_B"
    CLASS_C = "CLASS_C"


class LoopState(StrEnum):
    """State machine states for the learning-evolution loop."""

    IDLE = "IDLE"
    COMPUTING = "COMPUTING"
    VALIDATING = "VALIDATING"
    APPLYING = "APPLYING"
    QUEUED = "QUEUED"


@dataclass(frozen=True, slots=True)
class MutationProposal:
    """A proposed parameter mutation with class and provenance."""

    mutation_class: MutationClass
    parameter_path: str
    old_value: str
    new_value: str
    source_engine: str
    rationale: str
    ts_ns: int


class LearningEvolutionLoop:
    """FSM for the learning-evolution closed loop.

    Governs the flow of mutations from proposal through validation
    to application, respecting mutation class gates.

    Uses private fields to prevent external state bypass — transitions
    must go through the public API methods only.
    """

    __slots__ = ("_state", "_pending_proposals")

    def __init__(self) -> None:
        self._state: LoopState = LoopState.IDLE
        self._pending_proposals: list[MutationProposal] = []

    @property
    def state(self) -> LoopState:
        return self._state

    @property
    def pending_proposals(self) -> list[MutationProposal]:
        return list(self._pending_proposals)

    def propose(self, proposal: MutationProposal) -> str:
        """Submit a mutation proposal. Returns disposition.

        Class A: auto-apply if learning is enabled.
        Class B: queue for paper-scope application.
        Class C: reject (operator must use dashboard).
        """
        if proposal.mutation_class == MutationClass.CLASS_C:
            return "REJECTED_OPERATOR_ONLY"

        # Only accept new proposals from IDLE or COMPUTING; reject if mid-apply
        if self._state in (LoopState.APPLYING, LoopState.VALIDATING):
            return "REJECTED_LOOP_BUSY"

        self._pending_proposals.append(proposal)
        self._state = LoopState.COMPUTING
        return "ACCEPTED"

    def validate(self) -> list[MutationProposal]:
        """Move proposals from COMPUTING to VALIDATING.

        Structural + semantic sanity checks — proposals that fail are
        dropped with no retry. Returns the list of proposals that passed.

        Checks applied:
        1. parameter_path must be non-empty
        2. old_value != new_value (no-op mutations are rejected)
        3. ts_ns must be positive
        4. source_engine must be non-empty
        5. rationale must be non-empty (every mutation needs justification)
        6. If new_value is numeric: must be finite and not extreme (|x|<1e9)
        """
        import math

        self._state = LoopState.VALIDATING
        valid: list[MutationProposal] = []
        for p in self._pending_proposals:
            if not p.parameter_path.strip():
                continue
            if p.old_value == p.new_value:
                continue
            if p.ts_ns <= 0:
                continue
            if not p.source_engine.strip():
                continue
            if not p.rationale.strip():
                continue
            # Numeric value guard: if new_value looks like a number,
            # reject NaN / ±inf and pathologically large values that
            # indicate a failed gradient step or unscaled weight.
            try:
                fval = float(p.new_value)
                if not math.isfinite(fval):
                    continue
                if abs(fval) > 1e9:
                    continue
            except (ValueError, TypeError):
                pass  # non-numeric string parameter — skip numeric check
            valid.append(p)
        self._pending_proposals = valid
        return list(valid)

    def apply_class_a(
        self,
        *,
        learning_enabled: bool,
    ) -> list[MutationProposal]:
        """Apply all Class A mutations if learning is enabled.

        Returns applied proposals.
        """
        if not learning_enabled:
            return []

        applied = [p for p in self._pending_proposals if p.mutation_class == MutationClass.CLASS_A]
        self._pending_proposals = [
            p for p in self._pending_proposals if p.mutation_class != MutationClass.CLASS_A
        ]
        self._state = LoopState.IDLE if not self._pending_proposals else LoopState.QUEUED
        return applied

    def apply_class_b(
        self,
        *,
        practice_enabled: bool,
    ) -> list[MutationProposal]:
        """Apply Class B mutations (paper-scoped during build-out).

        Returns applied proposals.
        """
        if not practice_enabled:
            return []

        applied = [p for p in self._pending_proposals if p.mutation_class == MutationClass.CLASS_B]
        self._pending_proposals = [
            p for p in self._pending_proposals if p.mutation_class != MutationClass.CLASS_B
        ]
        if not self._pending_proposals:
            self._state = LoopState.IDLE
        return applied

    def drain(self) -> None:
        """Reset to IDLE, clearing any remaining proposals."""
        self._pending_proposals.clear()
        self._state = LoopState.IDLE
