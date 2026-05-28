"""
core/contracts/intelligence.py
DIX VISION v42.2 — Intelligence Engine Protocol Contracts

Defines the structural typing contracts that any intelligence provider
must satisfy. Used for runtime type checking and dependency inversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class SignalDirection(StrEnum):
    """Directional signal output from intelligence evaluation."""

    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class ConfidenceBand(StrEnum):
    """Discrete confidence bands for signal strength."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    ZERO = "ZERO"


@dataclass(frozen=True, slots=True)
class IntelligenceSignal:
    """Output produced by an intelligence evaluator."""

    direction: SignalDirection
    confidence: float
    band: ConfidenceBand
    source: str
    symbol: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class LearningSample:
    """Input consumed by intelligence learning methods."""

    signal_id: str
    outcome_pnl: float
    regime_at_signal: str
    latency_ms: float
    ts_ns: int


@runtime_checkable
class IIntelligence(Protocol):
    """Protocol: intelligence engine contract.

    Any class implementing this protocol can serve as a signal provider
    in the DIXVISION execution pipeline. The governance engine validates
    that signal sources satisfy this protocol before routing.
    """

    def evaluate(self, market_state: dict[str, float]) -> IntelligenceSignal:
        """Produce a directional trading signal from market state.

        Args:
            market_state: Mapping of indicator names to current values.

        Returns:
            Frozen IntelligenceSignal with direction, confidence, source.
        """
        ...

    def learn(self, sample: LearningSample) -> bool:
        """Ingest a learning sample to update internal model parameters.

        Args:
            sample: Frozen LearningSample with signal outcome data.

        Returns:
            True if the model was updated, False if sample was rejected.
        """
        ...

    @property
    def name(self) -> str:
        """Unique identifier for this intelligence provider."""
        ...

    @property
    def confidence_floor(self) -> float:
        """Minimum confidence threshold below which signals are suppressed."""
        ...


@runtime_checkable
class IMetaController(Protocol):
    """Protocol: meta-controller that arbitrates between multiple signal sources."""

    def allocate(self, signals: list[IntelligenceSignal]) -> IntelligenceSignal:
        """Fuse multiple signals into a single consensus signal."""
        ...

    def update_weights(self, performance: dict[str, float]) -> None:
        """Adjust source weights based on recent performance."""
        ...


__all__ = [
    "ConfidenceBand",
    "IIntelligence",
    "IMetaController",
    "IntelligenceSignal",
    "LearningSample",
    "SignalDirection",
]
