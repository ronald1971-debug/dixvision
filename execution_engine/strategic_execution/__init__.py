"""execution_engine.strategic_execution — game-theoretic + optimal execution (NEW v3-P10)."""

from __future__ import annotations

from execution_engine.strategic_execution.adversarial_executor import AdversarialExecutor, AdversarialPlan
from execution_engine.strategic_execution.optimal_execution import OptimalExecutionPlan, OptimalExecutor
from execution_engine.strategic_execution.market_impact import (
    ImpactModel, ImpactEstimate,
    DepthEstimator, DepthSnapshot,
    SlippageCurve, SlippagePoint,
)

__all__ = [
    "AdversarialExecutor", "AdversarialPlan",
    "OptimalExecutionPlan", "OptimalExecutor",
    "ImpactModel", "ImpactEstimate",
    "DepthEstimator", "DepthSnapshot",
    "SlippageCurve", "SlippagePoint",
]
