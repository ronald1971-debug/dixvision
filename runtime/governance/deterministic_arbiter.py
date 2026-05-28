"""Deterministic Arbiter — same inputs → same decision (CONVERGENCE PILLAR 3).

Guarantees that governance decisions are reproducible:
- Given the same RuntimeSnapshot version
- Given the same intent data
- The arbiter MUST produce the same verdict

This is critical for:
1. Replay determinism (Pillar 4)
2. Audit verification (prove a decision was correct)
3. Testing (deterministic policy tests)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from runtime.authority import RuntimeSnapshot
from runtime.governance.enforcement_gate import GovernanceDecision


@dataclass(frozen=True, slots=True)
class ArbiterInput:
    """Canonical input for deterministic arbitration.

    All fields that influence the decision MUST be captured here.
    No external state, no randomness, no time-dependence.
    """

    intent_id: str
    intent_data_hash: str  # SHA-256 of canonical JSON
    state_version: int
    system_mode: str
    health_score: float
    live_execution_blocked: bool
    freeze_active: bool
    active_hazards: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeterminismProof:
    """Proof that a decision is deterministic.

    Contains the input hash + decision hash. If you replay with the
    same input hash, you MUST get the same decision hash.
    """

    input_hash: str
    decision_hash: str
    verified: bool


def canonicalize_input(
    *,
    intent_id: str,
    intent_data: dict[str, object],
    snapshot: RuntimeSnapshot,
) -> ArbiterInput:
    """Create a canonical input from intent + snapshot.

    The intent_data is hashed (not stored) to ensure determinism
    depends only on content, not dict ordering.
    """
    # Canonical JSON-like hash of intent data
    sorted_items = sorted((str(k), str(v)) for k, v in intent_data.items())
    data_str = "|".join(f"{k}={v}" for k, v in sorted_items)
    data_hash = hashlib.sha256(data_str.encode()).hexdigest()

    return ArbiterInput(
        intent_id=intent_id,
        intent_data_hash=data_hash,
        state_version=snapshot.version,
        system_mode=snapshot.system_mode,
        health_score=snapshot.health_score,
        live_execution_blocked=snapshot.live_execution_blocked,
        freeze_active=snapshot.freeze_active,
        active_hazards=snapshot.active_hazards,
    )


def verify_determinism(
    *,
    input_a: ArbiterInput,
    decision_a: GovernanceDecision,
    input_b: ArbiterInput,
    decision_b: GovernanceDecision,
) -> DeterminismProof:
    """Verify that two evaluations with the same input produce the same decision.

    Used during replay to assert governance decisions are reproducible.
    """
    input_hash_a = _hash_input(input_a)
    input_hash_b = _hash_input(input_b)
    decision_hash_a = _hash_decision(decision_a)
    decision_hash_b = _hash_decision(decision_b)

    same_input = input_hash_a == input_hash_b
    same_decision = decision_hash_a == decision_hash_b

    return DeterminismProof(
        input_hash=input_hash_a,
        decision_hash=decision_hash_a,
        verified=same_input and same_decision,
    )


def _hash_input(inp: ArbiterInput) -> str:
    """Deterministic hash of arbiter input."""
    parts = (
        inp.intent_id,
        inp.intent_data_hash,
        str(inp.state_version),
        inp.system_mode,
        f"{inp.health_score:.6f}",
        str(inp.live_execution_blocked),
        str(inp.freeze_active),
        "|".join(inp.active_hazards),
    )
    content = ":".join(parts).encode()
    return hashlib.sha256(content).hexdigest()


def _hash_decision(dec: GovernanceDecision) -> str:
    """Deterministic hash of a governance decision."""
    parts = (
        dec.verdict.value,
        dec.intent_id,
        str(dec.state_version),
        dec.reason,
    )
    content = ":".join(parts).encode()
    return hashlib.sha256(content).hexdigest()
