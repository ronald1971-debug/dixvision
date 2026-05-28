"""BotClassifier — identifies algorithmic opponents in the market.

Classifies market participants by their trading patterns:
- Market makers (HFT): tight quotes, high cancel rate, symmetric flow
- Momentum bots: chase price, enter on breakout, stop on reversal
- Arbitrage bots: cross-venue trades, minimal directional bias
- Toxic flow: informed traders consistently on the right side
- Retail: erratic timing, round lot sizes, emotional patterns
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ParticipantType(StrEnum):
    MARKET_MAKER = "MARKET_MAKER"
    MOMENTUM_BOT = "MOMENTUM_BOT"
    ARBITRAGE_BOT = "ARBITRAGE_BOT"
    TOXIC_FLOW = "TOXIC_FLOW"
    RETAIL = "RETAIL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class BotProfile:
    """Classification of a market participant."""

    participant_id: str
    classification: ParticipantType
    confidence: float
    features: dict[str, float]
    threat_level: float  # [0, 1] how dangerous is this participant
    description: str


class BotClassifier:
    """Classifies market participants from their trading behavior.

    Uses behavioral features to identify the type of counterparty
    we're trading against. Helps avoid toxic flow and predict
    opponent behavior.
    """

    def classify(
        self,
        participant_id: str,
        *,
        cancel_rate: float,  # [0, 1] fraction of orders cancelled
        avg_hold_time_ms: float,
        order_size_variance: float,  # coefficient of variation
        directional_bias: float,  # [-1, 1] net direction
        trades_per_second: float,
        profitability_vs_mid: float,  # are they consistently profitable?
        cross_venue_activity: float,  # [0, 1]
    ) -> BotProfile:
        """Classify a participant based on behavioral features."""
        features = {
            "cancel_rate": cancel_rate,
            "avg_hold_time_ms": avg_hold_time_ms,
            "size_variance": order_size_variance,
            "directional_bias": directional_bias,
            "trades_per_second": trades_per_second,
            "profitability_vs_mid": profitability_vs_mid,
            "cross_venue": cross_venue_activity,
        }

        # Rule-based classification
        if cancel_rate > 0.8 and trades_per_second > 10 and abs(directional_bias) < 0.1:
            return BotProfile(
                participant_id=participant_id,
                classification=ParticipantType.MARKET_MAKER,
                confidence=0.85,
                features=features,
                threat_level=0.3,
                description="High cancel rate + symmetric flow = market maker.",
            )

        if profitability_vs_mid > 0.6 and avg_hold_time_ms < 100:
            return BotProfile(
                participant_id=participant_id,
                classification=ParticipantType.TOXIC_FLOW,
                confidence=0.80,
                features=features,
                threat_level=0.9,
                description="Consistently profitable with short holds = toxic/informed flow.",
            )

        if cross_venue_activity > 0.7 and abs(directional_bias) < 0.15:
            return BotProfile(
                participant_id=participant_id,
                classification=ParticipantType.ARBITRAGE_BOT,
                confidence=0.75,
                features=features,
                threat_level=0.2,
                description="Cross-venue + neutral direction = arbitrage bot.",
            )

        if abs(directional_bias) > 0.5 and trades_per_second > 5:
            return BotProfile(
                participant_id=participant_id,
                classification=ParticipantType.MOMENTUM_BOT,
                confidence=0.70,
                features=features,
                threat_level=0.5,
                description="Strong directional bias + high frequency = momentum bot.",
            )

        if order_size_variance > 2.0 and avg_hold_time_ms > 60000:
            return BotProfile(
                participant_id=participant_id,
                classification=ParticipantType.RETAIL,
                confidence=0.65,
                features=features,
                threat_level=0.1,
                description="Variable sizing + long holds = retail participant.",
            )

        return BotProfile(
            participant_id=participant_id,
            classification=ParticipantType.UNKNOWN,
            confidence=0.3,
            features=features,
            threat_level=0.4,
            description="Unable to classify with confidence.",
        )
