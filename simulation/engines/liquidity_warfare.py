"""simulation.engines.liquidity_warfare — Liquidity Warfare Engine (Stage 8).

Models systematic liquidity manipulation and erosion:

  Spoofing          — large orders placed and cancelled before execution
  Layering          — multiple price levels of fake depth withdrawn on approach
  Iceberg detection — real large orders hidden in small visible tranches
  Depth erosion     — genuine liquidity withdrawal under stress
  Market impact     — linear + square-root cost model

Liquidity index (0–100): 100 = deep, stable market; 0 = collapsed book.
Impact model: cost_bps = α × size + β × √size, where α/β vary with regime.
"""
from __future__ import annotations

import dataclasses
import math
import random
import threading
from collections import deque
from typing import Any


@dataclasses.dataclass(frozen=True, slots=True)
class LiquidityEvent:
    ts_ns:      int
    kind:       str    # SPOOF | LAYER | ICEBERG | DEPTH_EROSION | RECOVERY
    severity:   float  # 0-1
    depth_before: float
    depth_after:  float


class LiquidityWarfareEngine:
    """Tracks synthetic order book manipulation and liquidity erosion."""

    def __init__(self, seed: int = 77) -> None:
        self._rng            = random.Random(seed)
        self._depth_index    = 75.0          # 0-100
        self._spread_bps     = 2.0           # bid-ask spread in bps
        self._spoof_rate     = 0.12          # prob per tick
        self._layer_rate     = 0.08
        self._iceberg_rate   = 0.05
        self._erosion_rate   = 0.15
        self._impact_alpha   = 0.001         # linear cost coefficient
        self._impact_beta    = 0.005         # sqrt cost coefficient
        self._events: deque[LiquidityEvent] = deque(maxlen=200)
        self._spoof_count    = 0
        self._layer_count    = 0
        self._iceberg_count  = 0
        self._erosion_count  = 0
        self._tick_count     = 0
        self._lock           = threading.Lock()

    # ------------------------------------------------------------------
    def tick(self, ts_ns: int, market_vol: float = 0.02) -> None:
        try:
            with self._lock:
                self._tick_count += 1
                depth_before = self._depth_index

                # Vol widens spread and increases attack rates
                vol_factor = market_vol / 0.02  # normalised to baseline

                # Natural depth recovery
                self._depth_index = min(
                    100.0,
                    self._depth_index + self._rng.gauss(0.3, 0.1),
                )

                # Spoofing: flash large fake orders
                if self._rng.random() < self._spoof_rate * vol_factor:
                    severity = self._rng.uniform(0.05, 0.30)
                    self._depth_index -= severity * 10
                    self._spoof_count += 1
                    self._events.append(LiquidityEvent(
                        ts_ns = ts_ns, kind = "SPOOF",
                        severity = round(severity, 3),
                        depth_before = round(depth_before, 2),
                        depth_after  = round(self._depth_index, 2),
                    ))

                # Layering: multiple fake levels withdrawn
                if self._rng.random() < self._layer_rate * vol_factor:
                    severity = self._rng.uniform(0.10, 0.45)
                    self._depth_index -= severity * 15
                    self._layer_count += 1
                    self._events.append(LiquidityEvent(
                        ts_ns = ts_ns, kind = "LAYER",
                        severity = round(severity, 3),
                        depth_before = round(depth_before, 2),
                        depth_after  = round(self._depth_index, 2),
                    ))

                # Iceberg detection (informational — does not remove depth)
                if self._rng.random() < self._iceberg_rate:
                    self._iceberg_count += 1
                    self._events.append(LiquidityEvent(
                        ts_ns = ts_ns, kind = "ICEBERG",
                        severity = round(self._rng.uniform(0.0, 0.20), 3),
                        depth_before = round(self._depth_index, 2),
                        depth_after  = round(self._depth_index, 2),
                    ))

                # Depth erosion under vol stress
                if market_vol > 0.04 and self._rng.random() < self._erosion_rate:
                    severity = self._rng.uniform(0.20, 0.60)
                    self._depth_index -= severity * 20
                    self._erosion_count += 1
                    self._events.append(LiquidityEvent(
                        ts_ns = ts_ns, kind = "DEPTH_EROSION",
                        severity = round(severity, 3),
                        depth_before = round(depth_before, 2),
                        depth_after  = round(self._depth_index, 2),
                    ))

                self._depth_index = max(0.0, min(100.0, self._depth_index))

                # Spread widens as depth falls
                self._spread_bps = max(
                    0.5, 2.0 + (100.0 - self._depth_index) * 0.1 * vol_factor
                )
        except Exception:
            pass

    def impact_cost_bps(self, size_usd: float) -> float:
        """Market impact cost in basis points for given order size."""
        alpha = self._impact_alpha * (1.0 + (100.0 - self._depth_index) / 50.0)
        beta  = self._impact_beta  * (1.0 + (100.0 - self._depth_index) / 50.0)
        return round(alpha * size_usd + beta * math.sqrt(max(0.0, size_usd)), 4)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            events = [dataclasses.asdict(e) for e in list(self._events)[-20:]]
            return {
                "depth_index":    round(self._depth_index, 2),
                "spread_bps":     round(self._spread_bps,  3),
                "spoof_count":    self._spoof_count,
                "layer_count":    self._layer_count,
                "iceberg_count":  self._iceberg_count,
                "erosion_count":  self._erosion_count,
                "tick_count":     self._tick_count,
                "impact_1m_bps":  self.impact_cost_bps(1_000_000),
                "impact_10m_bps": self.impact_cost_bps(10_000_000),
                "recent_events":  events,
            }


# ── Singleton ──────────────────────────────────────────────────────────────────

_singleton: LiquidityWarfareEngine | None = None
_lock = threading.Lock()


def get_liquidity_warfare_engine() -> LiquidityWarfareEngine:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = LiquidityWarfareEngine()
    return _singleton


__all__ = ["LiquidityWarfareEngine", "LiquidityEvent",
           "get_liquidity_warfare_engine"]
