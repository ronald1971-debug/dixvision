"""intelligence_engine.opponent_model — opponent/crowd modelling (NEW v3.1)."""

from __future__ import annotations

from intelligence_engine.opponent_model.behavior_predictor import BehaviorPrediction, BehaviorPredictor
from intelligence_engine.opponent_model.crowd_density import CrowdDensityEstimate, CrowdDensityEstimator
from intelligence_engine.opponent_model.strategy_detector import DetectedStrategy, StrategyDetector

__all__ = [
    "BehaviorPrediction", "BehaviorPredictor",
    "CrowdDensityEstimate", "CrowdDensityEstimator",
    "DetectedStrategy", "StrategyDetector",
]
