"""HorizonEngine — multi-timeframe signal fusion.

Generates and fuses signals across 5 time horizons. Each horizon
provides a directional bias and confidence. The engine resolves
conflicts and produces a unified signal.

Fusion rules:
- Unanimous agreement → high confidence
- Majority agreement → moderate confidence
- Split → low confidence (reduce size or skip)
- Lower horizons defer to higher on direction, higher defer to lower on timing
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TimeHorizon(StrEnum):
    MICRO = "MICRO"  # microseconds-seconds (HFT)
    SCALP = "SCALP"  # seconds-minutes
    INTRADAY = "INTRADAY"  # minutes-hours
    SWING = "SWING"  # hours-days
    MACRO = "MACRO"  # days-weeks


class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


@dataclass(frozen=True, slots=True)
class HorizonSignal:
    """Signal from a single time horizon."""

    horizon: TimeHorizon
    direction: Direction
    strength: float  # [0, 1]
    confidence: float  # [0, 1]
    reason: str


@dataclass(frozen=True, slots=True)
class FusedSignal:
    """Multi-horizon fused signal."""

    symbol: str
    direction: Direction
    confidence: float
    horizon_agreement: float  # [0, 1] how much horizons agree
    dominant_horizon: TimeHorizon
    components: tuple[HorizonSignal, ...]
    conflict_description: str


class HorizonLayer:
    """A single time-horizon layer that generates signals.

    Each layer maintains its own state and generates directional signals
    based on data at its native timeframe.
    """

    def __init__(self, horizon: TimeHorizon) -> None:
        self._horizon = horizon
        self._last_signal: HorizonSignal | None = None

    @property
    def horizon(self) -> TimeHorizon:
        return self._horizon

    @property
    def last_signal(self) -> HorizonSignal | None:
        return self._last_signal

    def update(
        self,
        *,
        trend_direction: float,  # [-1, 1] negative=down, positive=up
        trend_strength: float,  # [0, 1]
        confidence: float,
        reason: str = "",
    ) -> HorizonSignal:
        """Update the layer with new data and produce a signal."""
        if trend_direction > 0.1:
            direction = Direction.LONG
        elif trend_direction < -0.1:
            direction = Direction.SHORT
        else:
            direction = Direction.FLAT

        signal = HorizonSignal(
            horizon=self._horizon,
            direction=direction,
            strength=trend_strength,
            confidence=confidence,
            reason=reason or f"{self._horizon} signal: {direction}",
        )
        self._last_signal = signal
        return signal


# Horizon weights for fusion (higher horizons have more weight on direction)
_HORIZON_WEIGHTS: dict[TimeHorizon, float] = {
    TimeHorizon.MICRO: 0.05,
    TimeHorizon.SCALP: 0.10,
    TimeHorizon.INTRADAY: 0.25,
    TimeHorizon.SWING: 0.35,
    TimeHorizon.MACRO: 0.25,
}


class HorizonEngine:
    """Fuses signals across multiple time horizons.

    Resolves directional conflicts using weighted voting:
    - Higher timeframes get more weight on direction
    - Lower timeframes get more weight on timing precision
    """

    def __init__(self) -> None:
        self._layers: dict[TimeHorizon, HorizonLayer] = {h: HorizonLayer(h) for h in TimeHorizon}

    @property
    def layers(self) -> dict[TimeHorizon, HorizonLayer]:
        return dict(self._layers)

    def update_layer(
        self,
        horizon: TimeHorizon,
        *,
        trend_direction: float,
        trend_strength: float,
        confidence: float,
        reason: str = "",
    ) -> HorizonSignal:
        """Update a specific horizon layer."""
        return self._layers[horizon].update(
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            confidence=confidence,
            reason=reason,
        )

    def fuse(self, symbol: str) -> FusedSignal:
        """Fuse all horizon signals into a unified view."""
        signals: list[HorizonSignal] = []
        for layer in self._layers.values():
            if layer.last_signal is not None:
                signals.append(layer.last_signal)

        if not signals:
            return FusedSignal(
                symbol=symbol,
                direction=Direction.FLAT,
                confidence=0.0,
                horizon_agreement=0.0,
                dominant_horizon=TimeHorizon.INTRADAY,
                components=(),
                conflict_description="No signals available.",
            )

        # Weighted voting
        long_weight = 0.0
        short_weight = 0.0
        flat_weight = 0.0

        for sig in signals:
            w = _HORIZON_WEIGHTS.get(sig.horizon, 0.1) * sig.confidence * sig.strength
            if sig.direction == Direction.LONG:
                long_weight += w
            elif sig.direction == Direction.SHORT:
                short_weight += w
            else:
                flat_weight += w

        total_weight = long_weight + short_weight + flat_weight
        if total_weight == 0:
            total_weight = 1.0

        # Determine direction
        if long_weight > short_weight and long_weight > flat_weight:
            direction = Direction.LONG
            max_w = long_weight
        elif short_weight > long_weight and short_weight > flat_weight:
            direction = Direction.SHORT
            max_w = short_weight
        else:
            direction = Direction.FLAT
            max_w = flat_weight

        # Agreement metric
        agreement = max_w / total_weight

        # Confidence = agreement × average signal confidence
        avg_conf = sum(s.confidence for s in signals) / len(signals)
        confidence = agreement * avg_conf

        # Dominant horizon (highest weight in winning direction)
        dominant = max(
            [s for s in signals if s.direction == direction] or signals,
            key=lambda s: _HORIZON_WEIGHTS.get(s.horizon, 0) * s.strength,
        )

        # Conflict description
        dirs = {s.direction for s in signals}
        if len(dirs) == 1:
            conflict = "All horizons agree."
        elif Direction.LONG in dirs and Direction.SHORT in dirs:
            n_long = sum(1 for s in signals if s.direction == Direction.LONG)
            n_short = sum(1 for s in signals if s.direction == Direction.SHORT)
            conflict = f"Conflict: {n_long} horizons LONG vs {n_short} SHORT."
        else:
            conflict = "Partial agreement across horizons."

        return FusedSignal(
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            horizon_agreement=agreement,
            dominant_horizon=dominant.horizon,
            components=tuple(signals),
            conflict_description=conflict,
        )
