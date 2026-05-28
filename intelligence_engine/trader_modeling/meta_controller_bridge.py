"""Meta-controller bridge (BUILD-DIRECTIVE §15 — TIS module 16).

Bridges the trader modeling system into the existing meta_controller.
Feeds trader atoms, philosophies, reliability scores, and narrative
alignment into Indira's decision weighting.

This is the integration point where trader intelligence meets
execution intelligence. The bridge does NOT make decisions — it
provides weighted inputs to the meta-controller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TraderModelingInput:
    """Input from trader modeling system to meta-controller."""

    # Top atoms for current regime, ranked by fitness
    regime_atoms: tuple[str, ...]
    # Weights from philosophy alignment
    philosophy_weights: dict[str, float]
    # Current narrative alignment strength
    narrative_confidence: float
    # Reliability-weighted trader signals
    trader_signals: dict[str, float]  # trader_id → signal strength
    # Cluster allocation recommendation
    cluster_allocation: dict[str, float]  # cluster_id → weight
    # Divergence alerts (Indira vs imitated traders)
    divergence_alerts: tuple[str, ...]
    # Overall composition confidence
    composition_confidence: float
    ts_ns: int


class MetaControllerBridge:
    """Bridge between trader modeling and meta-controller.

    The bridge aggregates outputs from all TIS modules into a single
    structured input that the meta-controller can consume. It handles:
    1. Atom selection for current regime
    2. Philosophy weighting based on alignment
    3. Reliability-adjusted signal aggregation
    4. Narrative-driven confidence scaling
    5. Divergence flagging for learning
    """

    def __init__(self) -> None:
        self._last_input: TraderModelingInput | None = None

    def build_input(
        self,
        *,
        regime: str,
        atom_fitness: dict[str, float],  # atom_id → fitness for regime
        philosophy_vectors: dict[str, tuple[float, ...]],  # trader → vector
        reliability_scores: dict[str, float],  # trader → reliability
        narrative_alignment: float,
        cluster_weights: dict[str, float],
        divergences: list[str],
        ts_ns: int,
    ) -> TraderModelingInput:
        """Build a structured input for the meta-controller.

        Aggregates all TIS module outputs into a single coherent signal.
        """
        # Select top atoms by regime fitness
        sorted_atoms = sorted(atom_fitness.items(), key=lambda x: x[1], reverse=True)
        regime_atoms = tuple(a[0] for a in sorted_atoms[:10])

        # Weight philosophies by reliability
        philosophy_weights: dict[str, float] = {}
        for trader_id, vector in philosophy_vectors.items():
            reliability = reliability_scores.get(trader_id, 0.5)
            # Weight = reliability * vector magnitude (proxy for conviction)
            magnitude = sum(v * v for v in vector) ** 0.5 if vector else 0.0
            philosophy_weights[trader_id] = reliability * magnitude

        # Reliability-weighted trader signals
        trader_signals: dict[str, float] = {}
        for trader_id, reliability in reliability_scores.items():
            if reliability > 0.5:
                trader_signals[trader_id] = reliability

        # Composition confidence from narrative + reliability
        avg_reliability = sum(reliability_scores.values()) / max(len(reliability_scores), 1)
        composition_confidence = 0.5 * narrative_alignment + 0.5 * avg_reliability

        inp = TraderModelingInput(
            regime_atoms=regime_atoms,
            philosophy_weights=philosophy_weights,
            narrative_confidence=narrative_alignment,
            trader_signals=trader_signals,
            cluster_allocation=cluster_weights,
            divergence_alerts=tuple(divergences),
            composition_confidence=min(composition_confidence, 1.0),
            ts_ns=ts_ns,
        )
        self._last_input = inp
        return inp

    @property
    def last_input(self) -> TraderModelingInput | None:
        """Most recently built input (for debugging/telemetry)."""
        return self._last_input

    def to_meta_controller_payload(self, inp: TraderModelingInput) -> dict[str, Any]:
        """Convert to the format expected by meta_controller.process()."""
        return {
            "trader_modeling": {
                "regime_atoms": list(inp.regime_atoms),
                "philosophy_weights": inp.philosophy_weights,
                "narrative_confidence": inp.narrative_confidence,
                "trader_signals": inp.trader_signals,
                "cluster_allocation": inp.cluster_allocation,
                "divergence_count": len(inp.divergence_alerts),
                "composition_confidence": inp.composition_confidence,
            }
        }
