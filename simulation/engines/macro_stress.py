"""simulation.engines.macro_stress — Macro Stress Library (Stage 8).

Nine macro stress scenarios, each with an intensity curve (0–1) and
configurable market impacts:

  RATE_SHOCK          — sudden central bank rate hike; bond vol spike
  BANKING_CRISIS      — credit contagion, interbank freeze
  GEOPOLITICAL_SHOCK  — supply-chain disruption, commodity spike
  DEFLATIONARY_SPIRAL — falling prices reinforce falling demand
  HYPERINFLATION      — currency debasement, commodity surge
  STAGFLATION         — vol + macro stress without growth
  LIQUIDITY_CRISIS    — USD funding squeeze, repo stress
  TECH_SECTOR_ROUT    — multiple-compression, momentum reversal
  CRYPTO_WINTER       — BTC down > 75%, altcoin extinction, low vol

Scenarios activate probabilistically or via operator injection.
Composite stress index (0–100): weighted sum of active intensities.
"""
from __future__ import annotations

import dataclasses
import random
import threading
from collections import deque
from typing import Any


@dataclasses.dataclass(frozen=True, slots=True)
class MacroScenario:
    name:              str
    active:            bool
    intensity:         float   # 0–1
    price_multiplier:  float   # how much price is amplified (negative = down)
    vol_multiplier:    float   # vol amplification
    liquidity_drain:   float   # 0–1 fraction of depth removed
    duration_bars:     int     # how long the scenario runs


@dataclasses.dataclass(frozen=True, slots=True)
class MacroEvent:
    ts_ns:    int
    kind:     str    # ACTIVATED | ESCALATED | DEESCALATED | EXPIRED
    scenario: str
    intensity: float


_SCENARIO_DEFS: dict[str, dict] = {
    "RATE_SHOCK": {
        "base_prob":        0.005,
        "base_duration":    80,
        "vol_multiplier":   2.5,
        "price_multiplier": -0.08,
        "liquidity_drain":  0.25,
    },
    "BANKING_CRISIS": {
        "base_prob":        0.002,
        "base_duration":    150,
        "vol_multiplier":   4.0,
        "price_multiplier": -0.20,
        "liquidity_drain":  0.55,
    },
    "GEOPOLITICAL_SHOCK": {
        "base_prob":        0.004,
        "base_duration":    60,
        "vol_multiplier":   2.0,
        "price_multiplier": -0.06,
        "liquidity_drain":  0.20,
    },
    "DEFLATIONARY_SPIRAL": {
        "base_prob":        0.002,
        "base_duration":    200,
        "vol_multiplier":   1.5,
        "price_multiplier": -0.12,
        "liquidity_drain":  0.30,
    },
    "HYPERINFLATION": {
        "base_prob":        0.001,
        "base_duration":    300,
        "vol_multiplier":   3.0,
        "price_multiplier": -0.15,
        "liquidity_drain":  0.40,
    },
    "STAGFLATION": {
        "base_prob":        0.003,
        "base_duration":    250,
        "vol_multiplier":   2.2,
        "price_multiplier": -0.10,
        "liquidity_drain":  0.35,
    },
    "LIQUIDITY_CRISIS": {
        "base_prob":        0.003,
        "base_duration":    100,
        "vol_multiplier":   3.5,
        "price_multiplier": -0.18,
        "liquidity_drain":  0.70,
    },
    "TECH_SECTOR_ROUT": {
        "base_prob":        0.006,
        "base_duration":    90,
        "vol_multiplier":   2.8,
        "price_multiplier": -0.25,
        "liquidity_drain":  0.30,
    },
    "CRYPTO_WINTER": {
        "base_prob":        0.004,
        "base_duration":    400,
        "vol_multiplier":   1.8,
        "price_multiplier": -0.75,
        "liquidity_drain":  0.50,
    },
}


class MacroStressEngine:
    """Probabilistic macro scenario catalog with composite stress index."""

    def __init__(self, seed: int = 13) -> None:
        self._rng    = random.Random(seed)
        self._active: dict[str, dict] = {}   # name → {intensity, bars_remaining}
        self._events: deque[MacroEvent] = deque(maxlen=300)
        self._stress_index  = 0.0
        self._stress_history: deque[float] = deque(maxlen=200)
        self._activation_count = 0
        self._tick_count = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def activate_scenario(self, name: str, ts_ns: int) -> bool:
        """Operator-triggered scenario activation. Returns True if activated."""
        if name not in _SCENARIO_DEFS:
            return False
        try:
            with self._lock:
                self._activate(name, ts_ns)
            return True
        except Exception:
            return False

    def _activate(self, name: str, ts_ns: int) -> None:
        dfn = _SCENARIO_DEFS[name]
        self._active[name] = {
            "intensity":       0.10,
            "bars_remaining":  dfn["base_duration"],
        }
        self._activation_count += 1
        self._events.append(MacroEvent(
            ts_ns=ts_ns, kind="ACTIVATED", scenario=name, intensity=0.10,
        ))

    def tick(self, ts_ns: int) -> None:
        try:
            with self._lock:
                self._tick_count += 1

                # Probabilistic new scenario activation
                for name, dfn in _SCENARIO_DEFS.items():
                    if name not in self._active:
                        if self._rng.random() < dfn["base_prob"]:
                            self._activate(name, ts_ns)

                # Update active scenarios
                expired = []
                for name, state in self._active.items():
                    dfn = _SCENARIO_DEFS[name]
                    remaining = state["bars_remaining"] - 1

                    # Intensity curve: ramp up 20%, plateau, ramp down 20%
                    duration = dfn["base_duration"]
                    elapsed  = duration - remaining
                    ramp     = int(duration * 0.2) or 1
                    if elapsed < ramp:
                        intensity = min(1.0, elapsed / ramp)
                    elif remaining < ramp:
                        intensity = max(0.0, remaining / ramp)
                    else:
                        intensity = 1.0
                    intensity += self._rng.gauss(0.0, 0.02)
                    intensity  = max(0.0, min(1.0, intensity))

                    state["intensity"]      = round(intensity, 4)
                    state["bars_remaining"] = remaining

                    if remaining <= 0:
                        expired.append(name)
                        self._events.append(MacroEvent(
                            ts_ns=ts_ns, kind="EXPIRED",
                            scenario=name, intensity=0.0,
                        ))
                    elif remaining % 20 == 0:
                        self._events.append(MacroEvent(
                            ts_ns=ts_ns, kind="ESCALATED",
                            scenario=name, intensity=intensity,
                        ))

                for name in expired:
                    del self._active[name]

                # Composite stress index
                weights = {
                    "BANKING_CRISIS": 2.0, "LIQUIDITY_CRISIS": 1.8,
                    "HYPERINFLATION": 1.5, "DEFLATIONARY_SPIRAL": 1.4,
                    "STAGFLATION": 1.2, "GEOPOLITICAL_SHOCK": 1.1,
                    "RATE_SHOCK": 1.0, "TECH_SECTOR_ROUT": 1.0,
                    "CRYPTO_WINTER": 0.8,
                }
                raw = sum(
                    state["intensity"] * weights.get(name, 1.0)
                    for name, state in self._active.items()
                )
                self._stress_index = min(100.0, raw * 100.0 / 2.0)
                self._stress_history.append(round(self._stress_index, 2))
        except Exception:
            pass

    def composite_vol_multiplier(self) -> float:
        mult = 1.0
        for name, state in self._active.items():
            mult *= 1.0 + (_SCENARIO_DEFS[name]["vol_multiplier"] - 1.0) * state["intensity"]
        return round(mult, 4)

    def composite_price_impact(self) -> float:
        impact = 0.0
        for name, state in self._active.items():
            impact += _SCENARIO_DEFS[name]["price_multiplier"] * state["intensity"]
        return round(impact, 6)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active_list = [
                MacroScenario(
                    name             = name,
                    active           = True,
                    intensity        = round(state["intensity"], 4),
                    price_multiplier = round(_SCENARIO_DEFS[name]["price_multiplier"], 4),
                    vol_multiplier   = round(_SCENARIO_DEFS[name]["vol_multiplier"], 2),
                    liquidity_drain  = round(_SCENARIO_DEFS[name]["liquidity_drain"], 2),
                    duration_bars    = state["bars_remaining"],
                )
                for name, state in self._active.items()
            ]
            inactive_names = [n for n in _SCENARIO_DEFS if n not in self._active]
            events = [dataclasses.asdict(e) for e in list(self._events)[-20:]]
            hist   = list(self._stress_history)[-50:]
            return {
                "stress_index":          round(self._stress_index, 2),
                "active_count":          len(self._active),
                "activation_count":      self._activation_count,
                "tick_count":            self._tick_count,
                "composite_vol_mult":    self.composite_vol_multiplier(),
                "composite_price_impact":self.composite_price_impact(),
                "active_scenarios":      [dataclasses.asdict(s) for s in active_list],
                "inactive_scenarios":    inactive_names,
                "stress_history":        hist,
                "recent_events":         events,
            }


# ── Singleton ──────────────────────────────────────────────────────────────────

_singleton: MacroStressEngine | None = None
_lock = threading.Lock()


def get_macro_stress_engine() -> MacroStressEngine:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = MacroStressEngine()
    return _singleton


__all__ = ["MacroStressEngine", "MacroScenario", "MacroEvent",
           "get_macro_stress_engine"]
