"""
operator_governance — Constitutional authority and operator sovereignty layer.

Priority in the architecture:
  - Development phases: P2 (co-equal with system governance)
  - Live deployment:    P3

Protections:
  1. Constitutional Authority   — operator retains supreme authority at all times
  2. Override Priority          — higher-priority overrides always supersede lower
  3. Escalation Gating          — autonomy escalation requires explicit operator consent
  4. Manual Lockout             — operator can halt any subsystem at any time
  5. Consent Routing            — no autonomous action without consent record
  6. Governance Visibility      — all governance actions remain visible to operator
"""

from operator_governance.engine import OperatorGovernanceEngine, get_operator_governance

__all__ = ["OperatorGovernanceEngine", "get_operator_governance"]
