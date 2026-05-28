"""SE-03 — square-root market impact model.

Estimates permanent + temporary price impact for a given order size
using the square-root law. Pure computation. INV-15. B1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["ImpactEstimate", "ImpactModel"]


@dataclass(frozen=True, slots=True)
class ImpactEstimate:
    symbol: str
    ts_ns: int
    qty: float
    adv: float
    temporary_bps: float
    permanent_bps: float
    total_bps: float


class ImpactModel:
    """Square-root market impact model.

    total_impact_bps = sigma * (qty / adv)^0.5 * scale
    Split into temporary (reverts after trade) and permanent (price shift).
    """

    def __init__(
        self,
        sigma_bps: float = 50.0,       # annualised vol proxy in bps
        temp_fraction: float = 0.6,     # fraction of impact that is temporary
        scale: float = 1.0,
    ) -> None:
        if not 0.0 < temp_fraction < 1.0:
            raise ValueError("temp_fraction must be in (0, 1)")
        self._sigma = sigma_bps
        self._temp_frac = temp_fraction
        self._scale = scale

    def estimate(
        self,
        symbol: str,
        ts_ns: int,
        qty: float,
        adv: float,
    ) -> ImpactEstimate:
        if adv <= 0:
            total_bps = 0.0
        else:
            pct_adv = qty / adv
            total_bps = self._sigma * math.sqrt(pct_adv) * self._scale
        temporary_bps = total_bps * self._temp_frac
        permanent_bps = total_bps * (1.0 - self._temp_frac)
        return ImpactEstimate(
            symbol=symbol,
            ts_ns=ts_ns,
            qty=qty,
            adv=adv,
            temporary_bps=temporary_bps,
            permanent_bps=permanent_bps,
            total_bps=total_bps,
        )
