"""Philosophy encoder (BUILD-DIRECTIVE §15 — TIS module 6).

Encodes trader philosophies into dense vector representations for
similarity search, clustering, and strategy composition.

Each trader's philosophy is a weighted combination of:
- Market worldview (trend, mean-revert, event-driven, etc.)
- Time horizon (scalper, swing, position, invest)
- Risk posture (aggressive, moderate, conservative)
- Domain expertise (crypto, equities, forex, commodities)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MarketWorldview(StrEnum):
    """Trader's primary market philosophy."""

    TREND_FOLLOWING = "TREND_FOLLOWING"
    MEAN_REVERSION = "MEAN_REVERSION"
    EVENT_DRIVEN = "EVENT_DRIVEN"
    MARKET_MAKING = "MARKET_MAKING"
    ARBITRAGE = "ARBITRAGE"
    MACRO = "MACRO"
    VALUE = "VALUE"
    MOMENTUM = "MOMENTUM"
    STATISTICAL = "STATISTICAL"


class TimeHorizon(StrEnum):
    """Trader's primary time horizon."""

    SCALPER = "SCALPER"
    DAY_TRADER = "DAY_TRADER"
    SWING = "SWING"
    POSITION = "POSITION"
    INVESTOR = "INVESTOR"


@dataclass(frozen=True, slots=True)
class PhilosophyVector:
    """Dense representation of a trader's philosophy."""

    trader_id: str
    worldview: MarketWorldview
    horizon: TimeHorizon
    risk_tolerance: float  # 0=conservative, 1=aggressive
    diversification_pref: float  # 0=concentrated, 1=diversified
    systematic_score: float  # 0=discretionary, 1=fully systematic
    domain_weights: dict[str, float]  # domain → expertise weight
    embedding: tuple[float, ...] = ()  # dense vector for FAISS


class PhilosophyEncoder:
    """Encodes trader philosophies into vector representations."""

    def encode(
        self,
        *,
        trader_id: str,
        worldview: MarketWorldview,
        horizon: TimeHorizon,
        risk_tolerance: float,
        diversification_pref: float,
        systematic_score: float,
        domains: dict[str, float],
    ) -> PhilosophyVector:
        """Encode a trader's philosophy into a vector."""
        # Simple embedding: concat of normalized features
        embedding = (
            float(list(MarketWorldview).index(worldview)) / len(MarketWorldview),
            float(list(TimeHorizon).index(horizon)) / len(TimeHorizon),
            risk_tolerance,
            diversification_pref,
            systematic_score,
        )
        return PhilosophyVector(
            trader_id=trader_id,
            worldview=worldview,
            horizon=horizon,
            risk_tolerance=risk_tolerance,
            diversification_pref=diversification_pref,
            systematic_score=systematic_score,
            domain_weights=domains,
            embedding=embedding,
        )
