"""
financial_governance — Capital integrity layer.

Priority in the architecture:
  - Development phases: P4 (lowest) — cognitive integrity comes first
  - Live deployment:    P2 (co-equal with operator sovereignty)

Trading does not begin until the operator explicitly enables it.
This layer guards the moment it does.

Protections:
  1. Exposure Guard       — net exposure within declared risk budgets
  2. Leverage Monitor     — leverage bounds never exceeded
  3. Liquidation Sentinel — liquidation distance early warning
  4. Execution Hazard     — execution path hazard detection
  5. Capital Throttle     — capital deployment rate limiting
  6. Kill Switch          — financial-layer emergency halt
"""

from financial_governance.engine import FinancialGovernanceEngine, get_financial_governance

__all__ = ["FinancialGovernanceEngine", "get_financial_governance"]
