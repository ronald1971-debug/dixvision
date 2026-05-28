"""Adversarial simulation scenarios for stress testing.

Modules:
- jax_lob_sim: JAX-accelerated limit order book simulation
- manipulation_detector: Market manipulation detection + adversarial scenario testing
"""

from simulation.adversarial.manipulation_detector import (
    AdversarialSimulator,
    ManipulationDetector,
    ManipulationType,
)

__all__ = [
    "AdversarialSimulator",
    "ManipulationDetector",
    "ManipulationType",
]
