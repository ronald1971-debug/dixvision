"""Bridge: OPA adapter → governance_engine.

Wires the Open Policy Agent adapter into the governance engine as
an additional policy evaluation backend. OPA policies run alongside
existing governance gates (kill switch, mode FSM, operator consent).

The bridge provides runtime policy evaluation for:
- Execution authorization (can this trade proceed?)
- Risk limit enforcement (within position/heat/drawdown limits?)
- Mode transition validation (is this mode change allowed?)
- Learning permissions (can the system self-modify?)
"""

from __future__ import annotations

from dataclasses import dataclass

from integrations.opa_adapter.policy import (
    OPAPolicyAdapter,
    PolicyDecision,
    PolicyDomain,
    PolicyInput,
)


@dataclass(frozen=True, slots=True)
class GovernanceVerdict:
    """Result of a governance policy check."""

    allowed: bool
    domain: str
    reasons: tuple[str, ...]
    policy_id: str
    evaluation_ms: float
    ts_ns: int


class OPAGovernanceBridge:
    """Bridge between OPA adapter and governance_engine.

    Provides:
    - Execution policy evaluation (pre-trade checks)
    - Risk policy evaluation (position limits, heat, drawdown)
    - Mode transition policy (LOCKED→SAFE→PAPER→LIVE)
    - Operator authority verification
    - Learning/evolution policy gates

    All verdicts are fail-closed: if OPA is unreachable or policy
    evaluation fails, the default is DENY.
    """

    def __init__(self) -> None:
        self._adapter = OPAPolicyAdapter()
        self._evaluation_count = 0
        self._deny_count = 0
        self._allow_count = 0

    def initialize(self) -> bool:
        """Initialize OPA connection."""
        return self._adapter.connect()

    # --- Execution Policy ---

    def can_execute(
        self,
        *,
        kill_switch: bool = False,
        mode: str = "PAPER",
        operator_approved: bool = False,
        symbol: str = "",
    ) -> GovernanceVerdict:
        """Check if an execution is allowed."""
        result = self._adapter.evaluate_execution(
            kill_switch=kill_switch,
            mode=mode,
            operator_approved=operator_approved,
        )
        self._record(result.decision)

        return GovernanceVerdict(
            allowed=result.decision == PolicyDecision.ALLOW,
            domain=PolicyDomain.EXECUTION.value,
            reasons=tuple(result.reasons),
            policy_id=result.policy_id,
            evaluation_ms=result.evaluation_ms,
            ts_ns=result.ts_ns,
        )

    # --- Risk Policy ---

    def check_risk_limits(
        self,
        *,
        position_size: float = 0.0,
        max_position_size: float = 100.0,
        portfolio_heat: float = 0.0,
        max_heat: float = 0.6,
        drawdown: float = 0.0,
        max_drawdown: float = 0.15,
    ) -> GovernanceVerdict:
        """Check if current risk levels are within policy limits."""
        result = self._adapter.evaluate_risk(
            position_size=position_size,
            max_position_size=max_position_size,
            portfolio_heat=portfolio_heat,
            max_heat=max_heat,
            drawdown=drawdown,
            max_drawdown=max_drawdown,
        )
        self._record(result.decision)

        return GovernanceVerdict(
            allowed=result.decision == PolicyDecision.ALLOW,
            domain=PolicyDomain.RISK.value,
            reasons=tuple(result.reasons),
            policy_id=result.policy_id,
            evaluation_ms=result.evaluation_ms,
            ts_ns=result.ts_ns,
        )

    # --- Mode Transition Policy ---

    def can_transition_mode(
        self,
        *,
        current_mode: str = "LOCKED",
        target_mode: str = "SAFE",
        operator_approved: bool = False,
    ) -> GovernanceVerdict:
        """Check if a mode transition is allowed."""
        policy_input = PolicyInput(
            domain=PolicyDomain.MODE_TRANSITION,
            action="transition_mode",
            subject="operator",
            resource="system_mode",
            context={
                "current_mode": current_mode,
                "target_mode": target_mode,
                "operator_approved": operator_approved,
            },
        )
        result = self._adapter.evaluate(policy_input)
        self._record(result.decision)

        return GovernanceVerdict(
            allowed=result.decision == PolicyDecision.ALLOW,
            domain=PolicyDomain.MODE_TRANSITION.value,
            reasons=tuple(result.reasons),
            policy_id=result.policy_id,
            evaluation_ms=result.evaluation_ms,
            ts_ns=result.ts_ns,
        )

    # --- Learning Policy ---

    def can_learn(
        self,
        *,
        learning_type: str = "parameter_update",
        confidence: float = 0.0,
        min_confidence: float = 0.7,
    ) -> GovernanceVerdict:
        """Check if a learning/evolution operation is allowed."""
        policy_input = PolicyInput(
            domain=PolicyDomain.LEARNING,
            action="learn",
            subject="learning_engine",
            resource="model_parameters",
            context={
                "learning_type": learning_type,
                "confidence": confidence,
                "min_confidence": min_confidence,
            },
        )
        result = self._adapter.evaluate(policy_input)
        self._record(result.decision)

        return GovernanceVerdict(
            allowed=result.decision == PolicyDecision.ALLOW,
            domain=PolicyDomain.LEARNING.value,
            reasons=tuple(result.reasons),
            policy_id=result.policy_id,
            evaluation_ms=result.evaluation_ms,
            ts_ns=result.ts_ns,
        )

    # --- Metrics ---

    @property
    def evaluation_count(self) -> int:
        """Total policy evaluations."""
        return self._evaluation_count

    @property
    def deny_rate(self) -> float:
        """Fraction of evaluations that resulted in DENY."""
        if self._evaluation_count == 0:
            return 0.0
        return self._deny_count / self._evaluation_count

    @property
    def allow_rate(self) -> float:
        """Fraction of evaluations that resulted in ALLOW."""
        if self._evaluation_count == 0:
            return 0.0
        return self._allow_count / self._evaluation_count

    def _record(self, decision: PolicyDecision) -> None:
        """Record evaluation outcome."""
        self._evaluation_count += 1
        if decision == PolicyDecision.ALLOW:
            self._allow_count += 1
        elif decision == PolicyDecision.DENY:
            self._deny_count += 1
