"""MAC-02 — latent hidden state inference.

Infers hidden market state (e.g. accumulation/distribution phase)
from price + volume features. Pure computation. INV-15. B1.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["HiddenState", "HiddenStateDetector"]

_STATES = ("accumulation", "markup", "distribution", "markdown", "unknown")


@dataclass(frozen=True, slots=True)
class HiddenState:
    ts_ns: int
    state: str
    confidence: float
    features: tuple[tuple[str, float], ...]


class HiddenStateDetector:
    """Detect Wyckoff-style hidden state from price/volume features."""

    def detect(
        self,
        ts_ns: int,
        *,
        price_trend: float,       # -1.0 to 1.0
        volume_trend: float,      # -1.0 to 1.0
        spread_trend: float,      # -1.0 to 1.0
        volatility: float,        # 0.0 to 1.0
    ) -> HiddenState:
        scores = {
            "accumulation": max(0.0, -price_trend) * 0.4 + max(0.0, volume_trend) * 0.4 + (1.0 - volatility) * 0.2,
            "markup": max(0.0, price_trend) * 0.5 + max(0.0, volume_trend) * 0.3 + (1.0 - volatility) * 0.2,
            "distribution": max(0.0, price_trend) * 0.3 + max(0.0, -volume_trend) * 0.4 + volatility * 0.3,
            "markdown": max(0.0, -price_trend) * 0.5 + max(0.0, -volume_trend) * 0.3 + volatility * 0.2,
        }
        total = sum(scores.values()) or 1e-6
        probs = {s: v / total for s, v in scores.items()}
        best = max(probs, key=lambda s: probs[s])
        conf = probs[best]
        state = best if conf >= 0.35 else "unknown"

        return HiddenState(
            ts_ns=ts_ns,
            state=state,
            confidence=conf if state != "unknown" else 0.0,
            features=tuple(sorted({
                "price_trend": price_trend,
                "volume_trend": volume_trend,
                "spread_trend": spread_trend,
                "volatility": volatility,
            }.items())),
        )
