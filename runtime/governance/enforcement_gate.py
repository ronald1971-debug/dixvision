"""Enforcement Gate — blocking synchronous governance (CONVERGENCE PILLAR 3).

This gate sits in the execution fabric's hot path. Every intent MUST
pass through it before reaching an adapter. The gate:

1. Evaluates all applicable policies against the current RuntimeSnapshot
2. Produces a GovernanceDecision (ALLOW / DENY / CONDITIONAL)
3. Signs the decision with HMAC
4. Returns the signed intent (or blocks it)

FAIL-CLOSED: If the gate cannot evaluate (error, timeout), the intent
is DENIED. No intent ever passes without a signed decision.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from enum import StrEnum, auto

from runtime.authority import RuntimeAuthorityStore


class GovernanceVerdict(StrEnum):
    """Possible governance decisions."""

    ALLOW = auto()
    DENY = auto()
    CONDITIONAL = auto()


@dataclass(frozen=True, slots=True)
class GovernanceDecision:
    """A cryptographically signed governance decision.

    The HMAC signature proves this decision was made by the governance
    engine for this specific intent at this specific state version.
    """

    verdict: GovernanceVerdict
    intent_id: str
    state_version: int
    reason: str
    policy_ids: tuple[str, ...]
    ts_ns: int
    signature: str  # HMAC-SHA256


@dataclass(frozen=True, slots=True)
class EnforcementResult:
    """Result of enforcement gate evaluation."""

    decision: GovernanceDecision
    passed: bool
    blocked_reason: str | None = None


class EnforcementGate:
    """Synchronous blocking governance gate.

    MUST be called for every intent before execution.
    Returns immediately with ALLOW or DENY (no async, no queuing).
    """

    def __init__(
        self,
        *,
        store: RuntimeAuthorityStore,
        signing_key: bytes = b"dix-governance-v42.2",
    ) -> None:
        self._store = store
        self._signing_key = signing_key
        self._policies: list[PolicyEvaluator] = []

    def register_policy(self, policy: PolicyEvaluator) -> None:
        """Register a policy for evaluation."""
        self._policies.append(policy)

    def enforce(
        self, *, intent_id: str, intent_data: dict[str, object], ts_ns: int
    ) -> EnforcementResult:
        """Evaluate all policies and produce a signed decision.

        FAIL-CLOSED: any error → DENY.
        """
        snap = self._store.snapshot

        # Evaluate all policies
        violations: list[str] = []
        applied_policies: list[str] = []

        for policy in self._policies:
            try:
                result = policy.evaluate(
                    intent_data=intent_data,
                    state_version=snap.version,
                    system_mode=snap.system_mode,
                    health_score=snap.health_score,
                    live_execution_blocked=snap.live_execution_blocked,
                    freeze_active=snap.freeze_active,
                )
                applied_policies.append(policy.policy_id)
                if not result.passed:
                    violations.append(result.reason)
            except Exception as exc:
                # Fail-closed: evaluation error → deny
                violations.append(f"POLICY_ERROR:{policy.policy_id}:{exc}")

        # Determine verdict
        if violations:
            verdict = GovernanceVerdict.DENY
            reason = "; ".join(violations)
        else:
            verdict = GovernanceVerdict.ALLOW
            reason = "all policies passed"

        # Sign the decision
        signature = self._sign(intent_id, snap.version, verdict.value, ts_ns)

        decision = GovernanceDecision(
            verdict=verdict,
            intent_id=intent_id,
            state_version=snap.version,
            reason=reason,
            policy_ids=tuple(applied_policies),
            ts_ns=ts_ns,
            signature=signature,
        )

        return EnforcementResult(
            decision=decision,
            passed=verdict == GovernanceVerdict.ALLOW,
            blocked_reason=reason if verdict != GovernanceVerdict.ALLOW else None,
        )

    def verify_signature(self, decision: GovernanceDecision) -> bool:
        """Verify a decision's HMAC signature."""
        expected = self._sign(
            decision.intent_id,
            decision.state_version,
            decision.verdict.value,
            decision.ts_ns,
        )
        return hmac.compare_digest(decision.signature, expected)

    def _sign(self, intent_id: str, version: int, verdict: str, ts_ns: int) -> str:
        """Produce HMAC-SHA256 signature for a decision."""
        message = f"{intent_id}:{version}:{verdict}:{ts_ns}".encode()
        return hmac.new(self._signing_key, message, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Policy evaluator protocol
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PolicyResult:
    """Result of a single policy evaluation."""

    passed: bool
    reason: str


class PolicyEvaluator:
    """Base class for governance policies.

    Subclass and implement evaluate() for specific policies.
    """

    policy_id: str = "base"

    def evaluate(
        self,
        *,
        intent_data: dict[str, object],
        state_version: int,
        system_mode: str,
        health_score: float,
        live_execution_blocked: bool,
        freeze_active: bool,
    ) -> PolicyResult:
        """Evaluate this policy against intent + state.

        Must return immediately (synchronous). No IO, no network.
        """
        return PolicyResult(passed=True, reason="default-allow")


# ---------------------------------------------------------------------------
# Built-in policies
# ---------------------------------------------------------------------------


class FreezeBlockPolicy(PolicyEvaluator):
    """Blocks all intents when system is frozen."""

    policy_id: str = "FREEZE_BLOCK"

    def evaluate(self, *, freeze_active: bool, **kwargs: object) -> PolicyResult:
        if freeze_active:
            return PolicyResult(passed=False, reason="system frozen")
        return PolicyResult(passed=True, reason="not frozen")


class ExecutionBlockPolicy(PolicyEvaluator):
    """Blocks live execution when BLOCKED."""

    policy_id: str = "EXECUTION_BLOCK"

    def evaluate(self, *, live_execution_blocked: bool, **kwargs: object) -> PolicyResult:
        if live_execution_blocked:
            return PolicyResult(passed=False, reason="live execution BLOCKED")
        return PolicyResult(passed=True, reason="execution allowed")


class HealthThresholdPolicy(PolicyEvaluator):
    """Blocks execution when health drops below threshold."""

    policy_id: str = "HEALTH_THRESHOLD"

    def __init__(self, *, min_health: float = 0.3) -> None:
        self._min_health = min_health

    def evaluate(self, *, health_score: float, **kwargs: object) -> PolicyResult:
        if health_score < self._min_health:
            return PolicyResult(
                passed=False,
                reason=f"health {health_score:.2f} below threshold {self._min_health}",
            )
        return PolicyResult(passed=True, reason="health acceptable")
