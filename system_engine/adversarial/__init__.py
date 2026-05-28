"""Adversarial Engine — "the market is trying to exploit you."

Top-tier systems assume adversarial market conditions:
- Manipulation detection (spoofing, layering, wash trading)
- Bot classification (identify algorithmic opponents)
- Trap pattern detection (fake breakouts, stop hunts)
- Predatory flow detection (toxic flow identification)

Without this: you get trapped, chase fake moves.
With this: you anticipate manipulation and avoid traps.
"""

from system_engine.adversarial.bot_classifier import BotClassifier, BotProfile
from system_engine.adversarial.manipulation_detector import (
    ManipulationAlert,
    ManipulationDetector,
    ManipulationType,
)
from system_engine.adversarial.trap_detector import TrapDetector, TrapSignal

__all__ = [
    "ManipulationDetector",
    "ManipulationAlert",
    "ManipulationType",
    "BotClassifier",
    "BotProfile",
    "TrapDetector",
    "TrapSignal",
]
