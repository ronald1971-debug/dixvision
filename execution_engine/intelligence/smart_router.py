"""SmartRouter — selects optimal execution venue/path.

For each order, evaluates available venues and selects the optimal
route based on: liquidity, fees, latency, fill probability.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Venue(StrEnum):
    BINANCE = "BINANCE"
    COINBASE = "COINBASE"
    KRAKEN = "KRAKEN"
    BYBIT = "BYBIT"
    OKX = "OKX"
    UNISWAP = "UNISWAP"
    RAYDIUM = "RAYDIUM"
    JUPITER = "JUPITER"
    INTERNAL = "INTERNAL"  # internal crossing


@dataclass(frozen=True, slots=True)
class VenueScore:
    """Scoring of a venue for a specific order."""

    venue: Venue
    liquidity_score: float  # [0, 1]
    fee_bps: float
    latency_ms: float
    fill_probability: float  # [0, 1]
    composite_score: float


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """Final routing decision."""

    symbol: str
    primary_venue: Venue
    fallback_venue: Venue | None
    scores: tuple[VenueScore, ...]
    reason: str


class SmartRouter:
    """Selects optimal execution venue for each order.

    Deterministic routing: same (order, venue_state) → same route.
    """

    def __init__(self) -> None:
        self._venue_configs: dict[Venue, dict[str, float]] = {
            Venue.BINANCE: {"fee_bps": 1.0, "latency_ms": 5, "reliability": 0.99},
            Venue.COINBASE: {"fee_bps": 5.0, "latency_ms": 15, "reliability": 0.98},
            Venue.KRAKEN: {"fee_bps": 2.6, "latency_ms": 20, "reliability": 0.97},
            Venue.BYBIT: {"fee_bps": 1.0, "latency_ms": 8, "reliability": 0.96},
            Venue.OKX: {"fee_bps": 0.8, "latency_ms": 10, "reliability": 0.95},
            Venue.UNISWAP: {"fee_bps": 30.0, "latency_ms": 12000, "reliability": 0.90},
            Venue.RAYDIUM: {"fee_bps": 25.0, "latency_ms": 400, "reliability": 0.85},
            Venue.JUPITER: {"fee_bps": 20.0, "latency_ms": 500, "reliability": 0.88},
        }
        self._venue_liquidity: dict[tuple[str, Venue], float] = {}

    def update_venue_liquidity(self, symbol: str, venue: Venue, liquidity_usd: float) -> None:
        """Update known liquidity at a venue for a symbol."""
        self._venue_liquidity[(symbol, venue)] = liquidity_usd

    def route(
        self,
        symbol: str,
        order_size_usd: float,
        *,
        urgency: float = 0.5,
        available_venues: list[Venue] | None = None,
    ) -> RouteDecision:
        """Select optimal venue for an order."""
        venues = available_venues or list(self._venue_configs.keys())
        scores: list[VenueScore] = []

        for venue in venues:
            config = self._venue_configs.get(venue)
            if config is None:
                continue

            liq = self._venue_liquidity.get((symbol, venue), 0.0)
            liq_score = min(liq / (order_size_usd * 10), 1.0) if order_size_usd > 0 else 0.5

            fill_prob = config["reliability"] * min(liq_score + 0.3, 1.0)

            # Composite: low fees + high liquidity + low latency + high fill
            composite = (
                (1.0 - config["fee_bps"] / 50.0) * 0.25
                + liq_score * 0.35
                + (1.0 - config["latency_ms"] / 15000.0) * (0.2 + urgency * 0.1)
                + fill_prob * 0.20
            )

            scores.append(
                VenueScore(
                    venue=venue,
                    liquidity_score=liq_score,
                    fee_bps=config["fee_bps"],
                    latency_ms=config["latency_ms"],
                    fill_probability=fill_prob,
                    composite_score=composite,
                )
            )

        scores.sort(key=lambda s: s.composite_score, reverse=True)

        primary = scores[0] if scores else None
        fallback = scores[1] if len(scores) > 1 else None

        return RouteDecision(
            symbol=symbol,
            primary_venue=primary.venue if primary else Venue.BINANCE,
            fallback_venue=fallback.venue if fallback else None,
            scores=tuple(scores),
            reason=(
                f"Best score: {primary.venue}={primary.composite_score:.3f}"
                if primary
                else "no_venues"
            ),
        )
