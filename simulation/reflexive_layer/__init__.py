"""Reflexive simulation layer — own-order feedback and crowding effects.

Modules:
- impact_feedback: Own-order price impact accumulation and decay (REFL-01)
- liquidity_decay: Liquidity drying up under our flow (REFL-02)
- crowd_density_sim: Alpha decay due to strategy crowding (REFL-03)
"""

from __future__ import annotations

from simulation.reflexive_layer.impact_feedback import ImpactFeedback
from simulation.reflexive_layer.liquidity_decay import LiquidityDecay
from simulation.reflexive_layer.crowd_density_sim import CrowdDensitySim

__all__ = [
    "ImpactFeedback",
    "LiquidityDecay",
    "CrowdDensitySim",
]
