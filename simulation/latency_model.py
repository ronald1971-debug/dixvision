"""simulation/latency_model.py
DIX VISION v42.2 — Simulation Latency Model

Models realistic order execution latency for simulation and backtesting.
Applies exchange-specific latency distributions (log-normal) to convert
submission timestamps into fill timestamps.

Pure functions + frozen dataclasses (INV-15). Deterministic seeding.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class VenueLatencyProfile(StrEnum):
    TIER1_CEX = "TIER1_CEX"       # Binance, Kraken: 50-200ms
    TIER2_CEX = "TIER2_CEX"       # IG, Oanda: 100-500ms
    DEX = "DEX"                    # Uniswap etc: 500-5000ms (block time)
    PAPER = "PAPER"                # instant
    CUSTOM = "CUSTOM"


_PROFILE_PARAMS: dict[VenueLatencyProfile, tuple[float, float]] = {
    # (mean_ms, std_ms) of log-normal distribution
    VenueLatencyProfile.TIER1_CEX: (80.0, 40.0),
    VenueLatencyProfile.TIER2_CEX: (200.0, 100.0),
    VenueLatencyProfile.DEX: (2000.0, 1500.0),
    VenueLatencyProfile.PAPER: (1.0, 0.0),
    VenueLatencyProfile.CUSTOM: (100.0, 50.0),
}


@dataclass(frozen=True, slots=True)
class LatencyConfig:
    """Latency model configuration for one venue."""
    venue: str
    profile: VenueLatencyProfile
    custom_mean_ms: float = 100.0
    custom_std_ms: float = 50.0
    network_jitter_pct: float = 0.1    # additional ±% jitter
    congestion_factor: float = 1.0     # multiplier during congestion


@dataclass(frozen=True, slots=True)
class LatencyDraw:
    """One sampled latency value."""
    venue: str
    latency_ms: float
    fill_ts_ns: int
    seed_used: int


def _lognormal_sample(mean_ms: float, std_ms: float, rng: random.Random) -> float:
    """Sample from a log-normal distribution fitted to mean and std."""
    if std_ms <= 0:
        return mean_ms
    cv = std_ms / mean_ms
    sigma = math.sqrt(math.log(1 + cv * cv))
    mu = math.log(mean_ms) - 0.5 * sigma * sigma
    return math.exp(mu + sigma * rng.gauss(0, 1))


class LatencyModel:
    """
    Samples execution latency from per-venue distributions.

    Deterministic when given an explicit seed — ensures INV-15 compliance
    in replay scenarios.
    """

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed
        self._rng = random.Random(seed)
        self._configs: dict[str, LatencyConfig] = {}

    def register_venue(self, config: LatencyConfig) -> None:
        self._configs[config.venue] = config

    def sample(
        self,
        venue: str,
        submission_ts_ns: int,
        seed_override: int | None = None,
    ) -> LatencyDraw:
        """Sample a latency draw for an order submission."""
        config = self._configs.get(venue)
        rng = random.Random(seed_override) if seed_override is not None else self._rng
        seed_used = seed_override if seed_override is not None else self._seed

        if config is None:
            # Default: TIER1_CEX profile
            mean_ms, std_ms = _PROFILE_PARAMS[VenueLatencyProfile.TIER1_CEX]
        elif config.profile == VenueLatencyProfile.CUSTOM:
            mean_ms, std_ms = config.custom_mean_ms, config.custom_std_ms
        else:
            mean_ms, std_ms = _PROFILE_PARAMS[config.profile]

        factor = config.congestion_factor if config else 1.0
        raw_ms = _lognormal_sample(mean_ms * factor, std_ms * factor, rng)

        # Add network jitter
        jitter_pct = config.network_jitter_pct if config else 0.1
        jitter = raw_ms * jitter_pct * (rng.random() * 2.0 - 1.0)
        latency_ms = max(0.1, raw_ms + jitter)

        fill_ts_ns = submission_ts_ns + int(latency_ms * 1_000_000)

        return LatencyDraw(
            venue=venue,
            latency_ms=latency_ms,
            fill_ts_ns=fill_ts_ns,
            seed_used=seed_used,
        )

    def deterministic_sample(
        self,
        venue: str,
        submission_ts_ns: int,
        sequence: int,
    ) -> LatencyDraw:
        """Deterministic sample based on venue + sequence number (INV-15)."""
        seed = int(hashlib.md5(f"{venue}:{sequence}".encode()).hexdigest()[:8], 16)
        return self.sample(venue, submission_ts_ns, seed_override=seed)

    def snapshot(self) -> dict[str, Any]:
        return {"venues": list(self._configs.keys())}


__all__ = [
    "LatencyConfig",
    "LatencyDraw",
    "LatencyModel",
    "VenueLatencyProfile",
]
