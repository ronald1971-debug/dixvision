"""OPP-02 — estimates positioning crowdedness.

Pure computation. INV-15. B1 compliant.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["CrowdDensityEstimate", "CrowdDensityEstimator"]


@dataclass(frozen=True, slots=True)
class CrowdDensityEstimate:
    ts_ns: int
    symbol: str
    crowding_score: float    # 0.0 = empty, 1.0 = max crowded
    direction: str           # "LONG", "SHORT", "NEUTRAL"
    participant_estimate: int
    detail: str = ""


class CrowdDensityEstimator:
    """Estimate crowd positioning from open-interest and volume features."""

    def __init__(
        self,
        long_oi_threshold: float = 0.65,
        short_oi_threshold: float = 0.35,
    ) -> None:
        self._long_thresh = long_oi_threshold
        self._short_thresh = short_oi_threshold

    def estimate(
        self,
        ts_ns: int,
        symbol: str,
        *,
        long_oi_fraction: float,   # 0.0–1.0 fraction of OI that is long
        volume_zscore: float = 0.0, # standardised volume relative to recent avg
    ) -> CrowdDensityEstimate:
        if long_oi_fraction >= self._long_thresh:
            direction = "LONG"
            crowding = min(1.0, (long_oi_fraction - self._long_thresh) / (1.0 - self._long_thresh))
        elif long_oi_fraction <= self._short_thresh:
            direction = "SHORT"
            crowding = min(1.0, (self._short_thresh - long_oi_fraction) / self._short_thresh)
        else:
            direction = "NEUTRAL"
            crowding = abs(long_oi_fraction - 0.5) * 2.0

        crowding = min(1.0, crowding * (1.0 + max(0.0, volume_zscore) * 0.1))
        participant_est = max(0, int(crowding * 1000))

        return CrowdDensityEstimate(
            ts_ns=ts_ns,
            symbol=symbol,
            crowding_score=crowding,
            direction=direction,
            participant_estimate=participant_est,
            detail=f"oi_long={long_oi_fraction:.2f} dir={direction}",
        )
