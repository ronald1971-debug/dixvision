"""trader_modeling — Behavioral trader intelligence pipeline.

Three-stage pipeline:
  ProfileExtractor → BehavioralClassifier → ArchetypePublisher

Orchestrated by TraderModelingRuntime.
"""

from trader_modeling.archetype_publisher import ArchetypePublisher, get_archetype_publisher
from trader_modeling.behavioral_classifier import (
    ALL_ARCHETYPES,
    BehavioralClassifier,
    ClassificationResult,
    get_behavioral_classifier,
)
from trader_modeling.profile_extractor import (
    ProfileExtractor,
    SignalBatch,
    TraderSignal,
    get_profile_extractor,
)
from trader_modeling.trader_modeling_runtime import (
    TraderModelingRuntime,
    get_trader_modeling_runtime,
)

__all__ = [
    "ALL_ARCHETYPES",
    "ArchetypePublisher",
    "BehavioralClassifier",
    "ClassificationResult",
    "ProfileExtractor",
    "SignalBatch",
    "TraderModelingRuntime",
    "TraderSignal",
    "get_archetype_publisher",
    "get_behavioral_classifier",
    "get_profile_extractor",
    "get_trader_modeling_runtime",
]
