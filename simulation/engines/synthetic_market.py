"""simulation.engines.synthetic_market — Synthetic Market Engine (Stage 8).

Generates realistic synthetic price series:
  GBM base            — log-normal returns with configurable drift/sigma
  Heston vol          — stochastic vol with mean-reversion (Euler-Maruyama)
  Merton jumps        — Poisson jump arrivals with Gaussian jump sizes
  Synthetic L2 book   — bid/ask/depth derived from current vol regime

INV-15: ts_ns always caller-supplied, never wall-clock.
INV-08: SyntheticBar, SyntheticBook are frozen+slotted.
"""
from __future__ import annotations

import dataclasses
import math
import random
import threading
from collections import deque
from typing import Any

_NS_PER_S = 1_000_000_000


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticBar:
    ts_ns: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    vol: float
    log_return: float


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticBook:
    ts_ns: int
    bid: float
    ask: float
    spread: float
    mid: float
    depth_score: float


class SyntheticMarketEngine:
    """GBM + Heston vol + Merton jump diffusion synthetic market."""

    def __init__(
        self,
        symbol: str = "SIM-USD",
        initial_price: float = 50_000.0,
        drift: float = 0.0001,
        sigma: float = 0.02,
        jump_intensity: float = 0.02,
        seed: int = 42,
    ) -> None:
        self._symbol          = symbol
        self._price           = initial_price
        self._drift           = drift
        self._sigma           = sigma
        self._current_vol     = sigma
        self._vol_of_vol      = 0.30
        self._kappa           = 0.10           # vol mean-reversion speed
        self._jump_intensity  = jump_intensity
        self._rng             = random.Random(seed)
        self._bars: deque[SyntheticBar] = deque(maxlen=200)
        self._book: SyntheticBook | None = None
        self._regime          = "NORMAL"
        self._tick_count      = 0
        self._jump_count      = 0
        self._lock            = threading.Lock()

    # ------------------------------------------------------------------
    def tick(self, ts_ns: int) -> None:
        try:
            with self._lock:
                self._tick_count += 1

                # Heston vol (Euler-Maruyama)
                dv = (
                    self._kappa * (self._sigma - self._current_vol) * 0.01
                    + self._vol_of_vol
                    * math.sqrt(max(self._current_vol, 1e-6))
                    * self._rng.gauss(0.0, 0.1)
                )
                self._current_vol = max(0.001, self._current_vol + dv)

                # GBM log-return
                z = self._rng.gauss(0.0, 1.0)
                log_ret = (
                    self._drift
                    - 0.5 * self._current_vol ** 2
                    + self._current_vol * z
                )

                # Merton jump
                if self._rng.random() < self._jump_intensity:
                    log_ret += self._rng.gauss(0.0, self._current_vol * 3.0)
                    self._jump_count += 1

                open_  = self._price
                close_ = open_ * math.exp(log_ret)
                sf     = abs(self._rng.gauss(0.0, self._current_vol * 0.5))
                high   = max(open_, close_) * (1.0 + sf)
                low    = min(open_, close_) * (1.0 - sf)
                vol_   = max(1.0, self._rng.gauss(1_000.0, 250.0))

                self._bars.append(SyntheticBar(
                    ts_ns      = ts_ns,
                    open       = round(open_,  2),
                    high       = round(high,   2),
                    low        = round(low,    2),
                    close      = round(close_, 2),
                    volume     = round(vol_,   2),
                    vol        = round(self._current_vol, 6),
                    log_return = round(log_ret, 6),
                ))
                self._price = close_

                # Synthetic L2 book
                half_spread = max(0.01, self._price * self._current_vol * 0.5)
                depth_score = max(0.0, 1.0 - self._current_vol / (self._sigma * 4.0))
                self._book  = SyntheticBook(
                    ts_ns       = ts_ns,
                    bid         = round(self._price - half_spread, 2),
                    ask         = round(self._price + half_spread, 2),
                    spread      = round(half_spread * 2.0, 4),
                    mid         = round(self._price, 2),
                    depth_score = round(depth_score, 4),
                )

                # Regime
                ratio = self._current_vol / max(self._sigma, 1e-9)
                if ratio < 0.5:
                    self._regime = "LOW_VOL"
                elif ratio < 1.5:
                    self._regime = "NORMAL"
                elif ratio < 2.5:
                    self._regime = "HIGH_VOL"
                else:
                    self._regime = "EXTREME_VOL"
        except Exception:
            pass

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            bars = list(self._bars)
            book = dataclasses.asdict(self._book) if self._book else {}
            price, vol, regime = self._price, self._current_vol, self._regime
            ticks, jumps, sigma = self._tick_count, self._jump_count, self._sigma

        returns      = [b.log_return for b in bars[-50:]]
        realized_vol = math.sqrt(
            sum(r ** 2 for r in returns) / max(1, len(returns))
        ) if returns else 0.0
        recent = [dataclasses.asdict(b) for b in bars[-20:]]

        return {
            "symbol":        self._symbol,
            "price":         round(price,       2),
            "current_vol":   round(vol,         6),
            "long_run_vol":  round(sigma,       6),
            "realized_vol":  round(realized_vol,6),
            "regime":        regime,
            "tick_count":    ticks,
            "jump_count":    jumps,
            "bar_count":     len(bars),
            "book":          book,
            "recent_bars":   recent,
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_singleton: SyntheticMarketEngine | None = None
_lock = threading.Lock()


def get_synthetic_market_engine() -> SyntheticMarketEngine:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = SyntheticMarketEngine()
    return _singleton


__all__ = ["SyntheticMarketEngine", "SyntheticBar", "SyntheticBook",
           "get_synthetic_market_engine"]
