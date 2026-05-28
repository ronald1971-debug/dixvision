"""
cognitive_governance — Phase 0–3 primary safety layer.

Protects cognitive integrity across four dimensions:
  1. Belief Integrity     (beliefs are calibrated and externally grounded)
  2. Memory Integrity     (vector stores are uncontaminated)
  3. Mutation Safety      (strategy evolution stays reversible)
  4. Epistemic Honesty    (learning is externally grounded)

Capital integrity (FinancialGovernance) becomes co-equal in Phase 4+
once live execution is real. Until then this IS the P0 safety stack.

P1 Enforcement surface:
  - cognitive_constitution  Gate decisions (block mutations/learning/signals)
  - learning_coherence      Composite coherence score across 6 dimensions
  - long_horizon_memory     Multi-week pattern tracking and identity drift
"""

from cognitive_governance.engine import CognitiveGovernanceEngine, get_cognitive_governance
from cognitive_governance.cognitive_constitution import (
    CognitiveConstitution,
    CognitiveGateKind,
    GateDecision,
    get_cognitive_constitution,
)
from cognitive_governance.learning_coherence import (
    CoherenceLevel,
    LearningCoherenceMonitor,
    LearningCoherenceScore,
    get_learning_coherence_monitor,
)
from cognitive_governance.long_horizon_memory import (
    LongHorizonMemoryStore,
    LongHorizonPattern,
    LongHorizonSnapshot,
    PatternKind,
    PatternState,
    get_long_horizon_memory,
)

__all__ = [
    # Engine
    "CognitiveGovernanceEngine",
    "get_cognitive_governance",
    # Constitution
    "CognitiveConstitution",
    "CognitiveGateKind",
    "GateDecision",
    "get_cognitive_constitution",
    # Coherence
    "CoherenceLevel",
    "LearningCoherenceMonitor",
    "LearningCoherenceScore",
    "get_learning_coherence_monitor",
    # Long-horizon memory
    "LongHorizonMemoryStore",
    "LongHorizonPattern",
    "LongHorizonSnapshot",
    "PatternKind",
    "PatternState",
    "get_long_horizon_memory",
]
