"""Trader abstraction normalizer (BUILD-DIRECTIVE §16 — module 4).

Normalizes raw trader data into canonical internal form before
encoding. Handles unit conversion, scale normalization, and
missing data imputation for the abstraction pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NormalizedTraderData:
    """Normalized trader data ready for encoding."""

    trader_id: str
    risk_tolerance: float  # normalized 0-1
    time_horizon: float  # normalized 0-1
    systematic_score: float  # normalized 0-1
    conviction_style: float  # normalized 0-1
    domain_weights: dict[str, float]  # normalized to sum=1
    market_models: tuple[str, ...]
    track_record_years: float
    credibility: float


class TraderAbstractionNormalizer:
    """Normalizes raw trader data for the abstraction pipeline.

    Handles:
    - Scale differences (different traders report differently)
    - Missing data (impute reasonable defaults)
    - Unit conversion (years, percentages, ratios)
    - Weight normalization (domain weights sum to 1)
    """

    # Time horizon normalization (years → 0-1 scale)
    _TIME_HORIZON_MAP = {
        "scalper": 0.05,
        "day_trader": 0.15,
        "swing": 0.35,
        "position": 0.6,
        "investor": 0.9,
    }

    def normalize(
        self,
        *,
        trader_id: str,
        raw_data: dict[str, Any],
    ) -> NormalizedTraderData:
        """Normalize raw trader data."""
        # Risk tolerance: accept various inputs
        risk_raw = raw_data.get("risk_tolerance")
        if risk_raw is None:
            risk_tolerance = 0.5  # default neutral
        elif isinstance(risk_raw, str):
            risk_map = {"low": 0.2, "medium": 0.5, "high": 0.8, "extreme": 0.95}
            risk_tolerance = risk_map.get(risk_raw.lower(), 0.5)
        else:
            risk_tolerance = max(0.0, min(1.0, float(risk_raw)))

        # Time horizon
        time_raw = raw_data.get("time_horizon", raw_data.get("timeframe"))
        if time_raw is None:
            time_horizon = 0.5
        elif isinstance(time_raw, str):
            time_horizon = self._TIME_HORIZON_MAP.get(time_raw.lower(), 0.5)
        else:
            time_horizon = max(0.0, min(1.0, float(time_raw)))

        # Systematic score
        sys_raw = raw_data.get("systematic_score", raw_data.get("systematic"))
        if sys_raw is None:
            systematic_score = 0.5
        elif isinstance(sys_raw, (bool,)):
            systematic_score = 1.0 if sys_raw else 0.0
        else:
            systematic_score = max(0.0, min(1.0, float(sys_raw)))

        # Conviction style
        conv_raw = raw_data.get("conviction_style", raw_data.get("concentration"))
        if conv_raw is None:
            conviction_style = 0.5
        else:
            conviction_style = max(0.0, min(1.0, float(conv_raw)))

        # Domain weights — normalize to sum=1
        domains_raw = raw_data.get("domain_weights", raw_data.get("domains", {}))
        if isinstance(domains_raw, dict):
            total = sum(float(v) for v in domains_raw.values()) or 1.0
            domain_weights = {str(k): float(v) / total for k, v in domains_raw.items()}
        else:
            domain_weights = {}

        # Market models
        models_raw = raw_data.get("market_models", raw_data.get("strategies", []))
        if isinstance(models_raw, (list, tuple)):
            market_models = tuple(str(m) for m in models_raw)
        else:
            market_models = ()

        # Track record
        track_years = float(raw_data.get("track_record_years", 0.0))

        # Credibility
        credibility = float(raw_data.get("credibility", raw_data.get("credibility_score", 0.5)))

        return NormalizedTraderData(
            trader_id=trader_id,
            risk_tolerance=risk_tolerance,
            time_horizon=time_horizon,
            systematic_score=systematic_score,
            conviction_style=conviction_style,
            domain_weights=domain_weights,
            market_models=market_models,
            track_record_years=track_years,
            credibility=credibility,
        )
