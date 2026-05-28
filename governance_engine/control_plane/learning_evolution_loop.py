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


@dataclass
class LearningEvolutionLoop:
    """FSM for the learning-evolution closed loop.

    Governs the flow of mutations from proposal through validation
    to application, respecting mutation class gates.
    """

    state: LoopState = LoopState.IDLE
    pending_proposals: list[MutationProposal] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.pending_proposals is None:
            self.pending_proposals = []

    def propose(self, proposal: MutationProposal) -> str:
        """Submit a mutation proposal. Returns disposition.

        Class A: auto-apply if learning is enabled.
        Class B: queue for paper-scope application.
        Class C: reject (operator must use dashboard).
        """
        if proposal.mutation_class == MutationClass.CLASS_C:
            return "REJECTED_OPERATOR_ONLY"

        self.pending_proposals.append(proposal)
        self.state = LoopState.COMPUTING
        return "ACCEPTED"

    def validate(self) -> list[MutationProposal]:
        """Move proposals from COMPUTING to VALIDATING.

        Returns proposals that passed validation.
        """
        self.state = LoopState.VALIDATING
        # All Class A/B proposals pass validation in the loop
        valid = list(self.pending_proposals)
        return valid

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

        applied = [p for p in self.pending_proposals if p.mutation_class == MutationClass.CLASS_A]
        self.pending_proposals = [
            p for p in self.pending_proposals if p.mutation_class != MutationClass.CLASS_A
        ]
        if not self.pending_proposals:
            self.state = LoopState.IDLE
        else:
            self.state = LoopState.QUEUED
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

        applied = [p for p in self.pending_proposals if p.mutation_class == MutationClass.CLASS_B]
        self.pending_proposals = [
            p for p in self.pending_proposals if p.mutation_class != MutationClass.CLASS_B
        ]
        if not self.pending_proposals:
            self.state = LoopState.IDLE
        return applied

    def drain(self) -> None:
        """Reset to IDLE, clearing any remaining proposals."""
        self.pending_proposals.clear()
        self.state = LoopState.IDLE
