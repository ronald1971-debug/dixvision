"""OPP-03 — infers in-market strategy populations.

Classifies the dominant strategy type present in the order flow.
Pure. INV-15. B1 compliant.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DetectedStrategy", "StrategyDetector"]


@dataclass(frozen=True, slots=True)
class DetectedStrategy:
    ts_ns: int
    symbol: str
    dominant_strategy: str    # "MOMENTUM", "MEAN_REVERSION", "MARKET_MAKING", "UNKNOWN"
    confidence: float
    secondary_strategy: str = ""
    detail: str = ""


class StrategyDetector:
    """Infer dominant strategy population from microstructure signals.

    Uses simple heuristics:
    - High autocorrelation in returns → MOMENTUM traders dominant
    - Negative autocorrelation → MEAN_REVERSION traders dominant
    - Tight spread + high fill rate → MARKET_MAKING dominant
    """

    def __init__(self, autocorr_threshold: float = 0.15) -> None:
        self._thresh = autocorr_threshold

    def detect(
        self,
        ts_ns: int,
        symbol: str,
        *,
        return_autocorr: float,    # lag-1 autocorrelation of returns
        spread_bps: float = 5.0,
        fill_rate: float = 0.5,    # fraction of orders filled at mid
    ) -> DetectedStrategy:
        strategies: list[tuple[str, float]] = []

        if return_autocorr > self._thresh:
            strategies.append(("MOMENTUM", return_autocorr))
        elif return_autocorr < -self._thresh:
            strategies.append(("MEAN_REVERSION", -return_autocorr))

        mm_score = max(0.0, (1.0 - spread_bps / 20.0) * fill_rate)
        if mm_score > 0.4:
            strategies.append(("MARKET_MAKING", mm_score))

        if not strategies:
            return DetectedStrategy(ts_ns, symbol, "UNKNOWN", 0.3)

        strategies.sort(key=lambda x: -x[1])
        dominant, conf = strategies[0]
        secondary = strategies[1][0] if len(strategies) > 1 else ""

        return DetectedStrategy(
            ts_ns=ts_ns,
            symbol=symbol,
            dominant_strategy=dominant,
            confidence=min(1.0, 0.3 + conf * 0.7),
            secondary_strategy=secondary,
            detail=f"autocorr={return_autocorr:.3f} mm_score={mm_score:.3f}",
        )
