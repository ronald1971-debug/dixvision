"""
cognitive_governance — Phase 0–3 primary safety layer.

Protects cognitive integrity across four dimensions:
  1. Belief Integrity     (beliefs are calibrated and externally grounded)
  2. Memory Integrity     (vector stores are uncontaminated)
  3. Mutation Safety      (strategy evolution stays reversible)
  4. Epistemic Honesty    (learning is externally grounded)

Capital integrity (FinancialGovernance) becomes co-equal in Phase 4+
once live execution is real. Until then this IS the P0 safety stack.
"""

from cognitive_governance.engine import CognitiveGovernanceEngine, get_cognitive_governance

__all__ = ["CognitiveGovernanceEngine", "get_cognitive_governance"]
