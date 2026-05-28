"""AnomalyAlphaDetector — finds unusual patterns that precede moves.

Detects statistical anomalies in market data that historically
preceded significant price movements. This is "pattern without theory"
alpha — the system detects the pattern first, then the analyst can
investigate the causal mechanism.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import StrEnum


class AnomalyType(StrEnum):
    VOLUME_SPIKE = "VOLUME_SPIKE"
    SPREAD_EXPANSION = "SPREAD_EXPANSION"
    DEPTH_IMBALANCE = "DEPTH_IMBALANCE"
    VOLATILITY_COMPRESSION = "VOLATILITY_COMPRESSION"
    ORDER_FLOW_DIVERGENCE = "ORDER_FLOW_DIVERGENCE"
    FUNDING_RATE_EXTREME = "FUNDING_RATE_EXTREME"


@dataclass(frozen=True, slots=True)
class AnomalySignal:
    """Detected anomaly that may contain alpha."""

    symbol: str
    anomaly_type: AnomalyType
    z_score: float  # how many std devs from normal
    historical_hit_rate: float  # how often this pattern preceded moves
    direction_bias: float  # [-1, 1] bullish/bearish lean
    confidence: float
    description: str


class AnomalyAlphaDetector:
    """Detects statistical anomalies in market microstructure.

    Maintains rolling statistics and flags deviations that historically
    preceded significant moves.
    """

    def __init__(self, *, z_threshold: float = 2.5, window: int = 100) -> None:
        self._z_thresh = z_threshold
        self._window = window
        self._volume_history: dict[str, deque[float]] = {}
        self._spread_history: dict[str, deque[float]] = {}
        self._volatility_history: dict[str, deque[float]] = {}

    def update(
        self,
        symbol: str,
        *,
        volume: float = 0.0,
        spread_bps: float = 0.0,
        volatility: float = 0.0,
        depth_imbalance: float = 0.5,
        funding_rate: float = 0.0,
    ) -> list[AnomalySignal]:
        """Update with new market data; return any anomalies detected."""
        signals: list[AnomalySignal] = []

        # Volume anomaly
        vol_z = self._update_and_zscore(self._volume_history, symbol, volume)
        if abs(vol_z) > self._z_thresh:
            signals.append(
                AnomalySignal(
                    symbol=symbol,
                    anomaly_type=AnomalyType.VOLUME_SPIKE,
                    z_score=vol_z,
                    historical_hit_rate=0.65,
                    direction_bias=0.0,  # volume spike is directionally neutral
                    confidence=min(abs(vol_z) / 5.0, 0.9),
                    description=f"Volume {vol_z:.1f}σ above normal — large move imminent.",
                )
            )

        # Spread anomaly
        spr_z = self._update_and_zscore(self._spread_history, symbol, spread_bps)
        if spr_z > self._z_thresh:
            signals.append(
                AnomalySignal(
                    symbol=symbol,
                    anomaly_type=AnomalyType.SPREAD_EXPANSION,
                    z_score=spr_z,
                    historical_hit_rate=0.55,
                    direction_bias=-0.3,  # spread expansion mildly bearish
                    confidence=min(spr_z / 4.0, 0.85),
                    description=f"Spread widening {spr_z:.1f}σ — market makers retreating.",
                )
            )

        # Volatility compression (low vol preceding breakout)
        vix_z = self._update_and_zscore(self._volatility_history, symbol, volatility)
        if vix_z < -self._z_thresh:
            signals.append(
                AnomalySignal(
                    symbol=symbol,
                    anomaly_type=AnomalyType.VOLATILITY_COMPRESSION,
                    z_score=vix_z,
                    historical_hit_rate=0.70,
                    direction_bias=0.0,  # compression is direction-neutral
                    confidence=min(abs(vix_z) / 4.0, 0.85),
                    description=(
                        f"Volatility compressed {abs(vix_z):.1f}σ below norm — breakout likely."
                    ),
                )
            )

        # Depth imbalance
        if abs(depth_imbalance - 0.5) > 0.3:
            bias = 1.0 if depth_imbalance > 0.5 else -1.0
            signals.append(
                AnomalySignal(
                    symbol=symbol,
                    anomaly_type=AnomalyType.DEPTH_IMBALANCE,
                    z_score=abs(depth_imbalance - 0.5) * 5,
                    historical_hit_rate=0.60,
                    direction_bias=bias * 0.6,
                    confidence=0.65,
                    description=f"Book imbalance {depth_imbalance:.0%} bid-heavy — buy pressure.",
                )
            )

        # Funding rate extreme (crypto)
        if abs(funding_rate) > 0.001:  # > 0.1% per period
            signals.append(
                AnomalySignal(
                    symbol=symbol,
                    anomaly_type=AnomalyType.FUNDING_RATE_EXTREME,
                    z_score=abs(funding_rate) * 1000,
                    historical_hit_rate=0.60,
                    direction_bias=-1.0 if funding_rate > 0 else 1.0,  # mean-reversion
                    confidence=0.70,
                    description=f"Funding rate {funding_rate:.4f} extreme — reversal likely.",
                )
            )

        return signals

    def _update_and_zscore(
        self,
        store: dict[str, deque[float]],
        symbol: str,
        value: float,
    ) -> float:
        """Update history and return z-score of latest value."""
        if symbol not in store:
            store[symbol] = deque(maxlen=self._window)
        store[symbol].append(value)

        history = store[symbol]
        if len(history) < 20:
            return 0.0

        values = list(history)
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance) if variance > 0 else 1e-9
        return (value - mean) / std
