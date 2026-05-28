"""Attribution Engine — "Why did we win/lose?"

PnL decomposition, decision attribution, mistake classifier, and
edge decay tracker. Answers the most important question in trading:
what actually caused each outcome?

Components:
- PnLDecomposer: breaks down PnL into alpha, beta, execution, timing
- DecisionAttributor: links outcomes to specific decisions/signals
- MistakeClassifier: categorizes errors for learning
- EdgeDecayTracker: detects when an edge is dying
"""

from learning_engine.attribution.decision_attributor import (
    Attribution,
    DecisionAttributor,
)
from learning_engine.attribution.edge_decay_tracker import EdgeDecayTracker, EdgeHealth
from learning_engine.attribution.mistake_classifier import (
    MistakeCategory,
    MistakeClassifier,
)
from learning_engine.attribution.outcome_linker import OutcomeLinker, PatternAttribution
from learning_engine.attribution.pnl_decomposer import PnLComponents, PnLDecomposer

__all__ = [
    "PnLDecomposer",
    "PnLComponents",
    "DecisionAttributor",
    "Attribution",
    "MistakeClassifier",
    "MistakeCategory",
    "EdgeDecayTracker",
    "EdgeHealth",
    "OutcomeLinker",
    "PatternAttribution",
]
