"""SlippagePredictor — estimates execution cost before placing an order.

Predicts expected slippage based on:
- Order size relative to available liquidity
- Current spread and depth
- Historical fill data
- Time of day / market conditions
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from execution_engine.intelligence.liquidity_model import LiquidityModel


@dataclass(frozen=True, slots=True)
class SlippageEstimate:
    """Predicted slippage for a potential order."""

    symbol: str
    order_size_usd: float
    estimated_slippage_bps: float
    confidence: float  # [0, 1] how confident in the estimate
    liquidity_sufficient: bool
    recommended_max_size_usd: float  # max size for < N bps slippage


class SlippagePredictor:
    """Predicts execution slippage before order placement.

    Model: slippage = spread/2 + impact_coefficient × sqrt(size / liquidity)
    (simplified Almgren-Chriss model)
    """

    def __init__(
        self,
        liquidity_model: LiquidityModel,
        *,
        impact_coefficient: float = 0.1,
        max_acceptable_slippage_bps: float = 10.0,
    ) -> None:
        self._liq = liquidity_model
        self._impact_coeff = impact_coefficient
        self._max_slip = max_acceptable_slippage_bps
        self._history: dict[str, deque[float]] = {}

    def predict(self, symbol: str, order_size_usd: float) -> SlippageEstimate:
        """Predict slippage for a potential order."""
        snap = self._liq.latest(symbol)
        if snap is None:
            return SlippageEstimate(
                symbol=symbol,
                order_size_usd=order_size_usd,
                estimated_slippage_bps=50.0,  # pessimistic default
                confidence=0.1,
                liquidity_sufficient=False,
                recommended_max_size_usd=0.0,
            )

        total_liquidity = snap.bid_depth_usd + snap.ask_depth_usd
        if total_liquidity <= 0:
            return SlippageEstimate(
                symbol=symbol,
                order_size_usd=order_size_usd,
                estimated_slippage_bps=100.0,
                confidence=0.2,
                liquidity_sufficient=False,
                recommended_max_size_usd=0.0,
            )

        # Almgren-Chriss simplified
        participation_rate = order_size_usd / total_liquidity
        impact = self._impact_coeff * math.sqrt(participation_rate) * 10000
        half_spread = snap.spread_bps / 2
        estimated_slip = half_spread + impact

        # Confidence based on data quality
        history = self._history.get(symbol)
        confidence = min(0.3 + (len(history) / 50 if history else 0), 0.9)

        # Recommended max size for acceptable slippage
        # Solve: max_slip = spread/2 + coeff * sqrt(size/liq) * 10000
        remaining = self._max_slip - half_spread
        if remaining > 0:
            max_participation = (remaining / (self._impact_coeff * 10000)) ** 2
            recommended_max = max_participation * total_liquidity
        else:
            recommended_max = 0.0

        return SlippageEstimate(
            symbol=symbol,
            order_size_usd=order_size_usd,
            estimated_slippage_bps=estimated_slip,
            confidence=confidence,
            liquidity_sufficient=estimated_slip < self._max_slip,
            recommended_max_size_usd=recommended_max,
        )

    def record_actual(self, symbol: str, actual_slippage_bps: float) -> None:
        """Record actual slippage for model calibration."""
        if symbol not in self._history:
            self._history[symbol] = deque(maxlen=200)
        self._history[symbol].append(actual_slippage_bps)
