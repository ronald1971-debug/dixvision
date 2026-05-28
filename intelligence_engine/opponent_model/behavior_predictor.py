"""OPP-01 — predicts likely trader actions from microstructure signals.

Pure computation. No wall-clock reads. B1 compliant. INV-15.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["BehaviorPrediction", "BehaviorPredictor"]


@dataclass(frozen=True, slots=True)
class BehaviorPrediction:
    ts_ns: int
    symbol: str
    predicted_action: str   # "BUY", "SELL", "HOLD", "CANCEL"
    confidence: float       # 0.0–1.0
    features_used: tuple[str, ...]
    detail: str = ""


class BehaviorPredictor:
    """Predict opponent trader actions from order-flow imbalance features.

    Uses a simple rule-based model (order-flow imbalance threshold) as
    the production default. The model is stateless per call — identical
    inputs produce identical predictions (INV-15).
    """

    def __init__(
        self,
        buy_imbalance_threshold: float = 0.6,
        sell_imbalance_threshold: float = 0.4,
        min_confidence: float = 0.3,
    ) -> None:
        self._buy_thresh = buy_imbalance_threshold
        self._sell_thresh = sell_imbalance_threshold
        self._min_conf = min_confidence

    def predict(
        self,
        ts_ns: int,
        symbol: str,
        *,
        order_flow_imbalance: float,  # 0.0 = full sell pressure, 1.0 = full buy pressure
        spread_bps: float = 0.0,
        trade_rate: float = 0.0,
    ) -> BehaviorPrediction:
        features: tuple[str, ...] = ("order_flow_imbalance",)
        if spread_bps > 0:
            features = (*features, "spread_bps")
        if trade_rate > 0:
            features = (*features, "trade_rate")

        if order_flow_imbalance >= self._buy_thresh:
            action = "BUY"
            confidence = min(1.0, 0.3 + order_flow_imbalance * 0.7)
        elif order_flow_imbalance <= self._sell_thresh:
            action = "SELL"
            confidence = min(1.0, 0.3 + (1.0 - order_flow_imbalance) * 0.7)
        else:
            action = "HOLD"
            confidence = 0.3 + abs(order_flow_imbalance - 0.5) * 0.4

        if confidence < self._min_conf:
            action = "HOLD"

        return BehaviorPrediction(
            ts_ns=ts_ns,
            symbol=symbol,
            predicted_action=action,
            confidence=confidence,
            features_used=features,
        )
