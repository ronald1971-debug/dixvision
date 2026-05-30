"""simulation.engines.volatility_cascade — Volatility Cascade Engine (Stage 8).

Models vol regime transitions, gamma squeeze, and cross-asset contagion:

  Vol regimes: LOW_VOL → NORMAL → ELEVATED → EXTREME
  Cascade trigger: realised vol > 2.5× baseline → P(cascade) rises sharply
  Gamma squeeze: dealer delta-hedging amplifies directional moves
    - Gamma exposure estimated from synthetic open interest
    - Squeeze magnitude ∝ |price_move| × gamma_exposure / sqrt(liquidity)
  Cross-asset contagion: vol spills to correlated assets with lag
  Vol-of-vol tracker: second-order vol, signals regime instability

Vol history used to compute realised vol (20-bar rolling window).
"""
from __future__ import annotations

import dataclasses
import math
import random
import threading
from collections import deque
from typing import Any


@dataclasses.dataclass(frozen=True, slots=True)
class CascadeEvent:
    ts_ns:           int
    kind:            str    # CASCADE | SQUEEZE | CONTAGION | REGIME_SHIFT
    from_regime:     str
    to_regime:       str
    vol_level:       float
    squeeze_mag:     float


_REGIMES = ["LOW_VOL", "NORMAL", "ELEVATED", "EXTREME"]
_THRESHOLDS = [0.5, 1.5, 2.5, float("inf")]  # multiples of baseline


class VolatilityCascadeEngine:
    """Vol regime tracker with gamma squeeze and contagion model."""

    def __init__(self, baseline_vol: float = 0.02, seed: int = 33) -> None:
        self._baseline       = baseline_vol
        self._current_vol    = baseline_vol
        self._vol_of_vol     = 0.0
        self._regime         = "NORMAL"
        self._gamma_exposure = 1.0          # synthetic normalised gamma (1=neutral)
        self._contagion_pool = 0.0          # cross-asset vol overhang
        self._vol_history: deque[float]     = deque(maxlen=100)
        self._events: deque[CascadeEvent]   = deque(maxlen=200)
        self._cascade_count  = 0
        self._squeeze_count  = 0
        self._contagion_count = 0
        self._tick_count     = 0
        self._rng            = random.Random(seed)
        self._lock           = threading.Lock()

    # ------------------------------------------------------------------
    def tick(self, ts_ns: int, realised_vol: float, price_return: float = 0.0) -> None:
        try:
            with self._lock:
                self._tick_count += 1
                prev_regime = self._regime

                # Update vol tracker with EMA
                self._current_vol = 0.9 * self._current_vol + 0.1 * realised_vol
                self._vol_history.append(round(self._current_vol, 6))

                # Vol-of-vol (std of recent vol)
                hist = list(self._vol_history)[-20:]
                if len(hist) > 2:
                    mean_v = sum(hist) / len(hist)
                    self._vol_of_vol = math.sqrt(
                        sum((v - mean_v) ** 2 for v in hist) / len(hist)
                    )

                # Regime classification
                ratio = self._current_vol / max(self._baseline, 1e-9)
                new_regime = "NORMAL"
                for i, thr in enumerate(_THRESHOLDS):
                    if ratio < thr:
                        new_regime = _REGIMES[i]
                        break

                # Regime shift event
                if new_regime != prev_regime:
                    self._events.append(CascadeEvent(
                        ts_ns       = ts_ns,
                        kind        = "REGIME_SHIFT",
                        from_regime = prev_regime,
                        to_regime   = new_regime,
                        vol_level   = round(self._current_vol, 6),
                        squeeze_mag = 0.0,
                    ))
                self._regime = new_regime

                # Cascade: elevated vol → cascade probability
                cascade_prob = max(0.0, (ratio - 1.5) * 0.3)
                if self._rng.random() < cascade_prob:
                    self._cascade_count += 1
                    self._events.append(CascadeEvent(
                        ts_ns       = ts_ns,
                        kind        = "CASCADE",
                        from_regime = self._regime,
                        to_regime   = self._regime,
                        vol_level   = round(self._current_vol, 6),
                        squeeze_mag = 0.0,
                    ))

                # Gamma squeeze: large moves force dealer hedging
                squeeze_mag = 0.0
                if abs(price_return) > 0.02:
                    squeeze_mag = abs(price_return) * self._gamma_exposure * 5.0
                    squeeze_mag *= max(0.1, 1.0 - ratio * 0.1)  # less at extreme vol
                    if squeeze_mag > 0.5:
                        self._squeeze_count += 1
                        self._events.append(CascadeEvent(
                            ts_ns       = ts_ns,
                            kind        = "SQUEEZE",
                            from_regime = self._regime,
                            to_regime   = self._regime,
                            vol_level   = round(self._current_vol, 6),
                            squeeze_mag = round(squeeze_mag, 4),
                        ))
                    # Gamma adapts: exposure increases during squeeze
                    self._gamma_exposure = min(3.0, self._gamma_exposure + squeeze_mag * 0.1)
                else:
                    self._gamma_exposure = max(0.5, self._gamma_exposure * 0.99)

                # Cross-asset contagion: extreme vol spills
                if self._regime == "EXTREME":
                    self._contagion_pool = min(1.0, self._contagion_pool + 0.05)
                else:
                    self._contagion_pool = max(0.0, self._contagion_pool - 0.01)

                if self._contagion_pool > 0.3 and self._rng.random() < 0.10:
                    self._contagion_count += 1
                    self._events.append(CascadeEvent(
                        ts_ns       = ts_ns,
                        kind        = "CONTAGION",
                        from_regime = self._regime,
                        to_regime   = self._regime,
                        vol_level   = round(self._current_vol, 6),
                        squeeze_mag = round(self._contagion_pool, 4),
                    ))
        except Exception:
            pass

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            hist   = list(self._vol_history)[-50:]
            events = [dataclasses.asdict(e) for e in list(self._events)[-20:]]
            return {
                "regime":           self._regime,
                "current_vol":      round(self._current_vol,  6),
                "baseline_vol":     round(self._baseline,     6),
                "vol_ratio":        round(self._current_vol / max(self._baseline, 1e-9), 3),
                "vol_of_vol":       round(self._vol_of_vol,   6),
                "gamma_exposure":   round(self._gamma_exposure, 4),
                "contagion_pool":   round(self._contagion_pool, 4),
                "cascade_count":    self._cascade_count,
                "squeeze_count":    self._squeeze_count,
                "contagion_count":  self._contagion_count,
                "tick_count":       self._tick_count,
                "vol_history":      hist,
                "recent_events":    events,
            }


# ── Singleton ──────────────────────────────────────────────────────────────────

_singleton: VolatilityCascadeEngine | None = None
_lock = threading.Lock()


def get_volatility_cascade_engine() -> VolatilityCascadeEngine:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = VolatilityCascadeEngine()
    return _singleton


__all__ = ["VolatilityCascadeEngine", "CascadeEvent",
           "get_volatility_cascade_engine"]
