"""simulation.engines.reflexive — Reflexive Simulation Engine (Stage 8).

Implements Soros-style market reflexivity:

  Cognitive function  — participants' biased perception of fundamentals
  Participating function — how perceptions feed back into fundamentals

  price_return → sentiment_shift (ρ) → buying_pressure → amplified_return
  When amplification exceeds threshold θ: CASCADE event
  When cascade exhausts: CORRECTION (mean-reversion burst)

The reflexivity coefficient ρ ∈ [0, 1] controls feedback intensity.
ρ→0: efficient market, no feedback.
ρ→1: fully reflexive, self-reinforcing feedback loops dominate.

INV-15: ts_ns always caller-supplied.
"""
from __future__ import annotations

import dataclasses
import math
import random
import threading
from collections import deque
from typing import Any


@dataclasses.dataclass(frozen=True, slots=True)
class ReflexiveEvent:
    ts_ns:      int
    kind:       str    # CASCADE | CORRECTION | EQUILIBRIUM
    rho:        float
    momentum:   float
    magnitude:  float


class ReflexiveSimulationEngine:
    """Soros reflexivity model with cascade and correction detection."""

    _CASCADE_THRESHOLD    = 0.65   # momentum above → cascade event
    _CORRECTION_THRESHOLD = -0.50  # momentum below → correction event
    _RHO_DECAY            = 0.02   # reflexivity cools per tick without reinforcement
    _RHO_REINFORCE        = 0.05   # each cascade tick adds this to rho

    def __init__(self, initial_rho: float = 0.30, seed: int = 11) -> None:
        self._rho          = initial_rho   # reflexivity coefficient
        self._sentiment    = 0.0           # −1 (fear) … +1 (greed)
        self._momentum     = 0.0           # cumulative directional pressure
        self._state        = "EQUILIBRIUM"
        self._cascade_count    = 0
        self._correction_count = 0
        self._tick_count       = 0
        self._rng              = random.Random(seed)
        self._events: deque[ReflexiveEvent] = deque(maxlen=200)
        self._rho_history: deque[float]     = deque(maxlen=200)
        self._lock             = threading.Lock()

    # ------------------------------------------------------------------
    def tick(self, ts_ns: int, price_return: float = 0.0) -> None:
        try:
            with self._lock:
                self._tick_count += 1

                # Participating function: return → sentiment shift
                raw_shift   = price_return * self._rho
                noise       = self._rng.gauss(0.0, 0.02)
                self._sentiment = max(-1.0, min(1.0,
                    self._sentiment * 0.92 + raw_shift + noise
                ))

                # Cognitive function: sentiment → buying pressure → return amplification
                amplification   = self._sentiment * self._rho
                self._momentum  = self._momentum * 0.85 + amplification

                # Reflexivity adapts: cascades reinforce ρ, otherwise ρ decays
                if abs(self._momentum) > self._CASCADE_THRESHOLD:
                    self._rho = min(0.95, self._rho + self._RHO_REINFORCE)
                else:
                    self._rho = max(0.05, self._rho - self._RHO_DECAY * 0.1)

                self._rho_history.append(round(self._rho, 4))

                # State machine
                if self._momentum > self._CASCADE_THRESHOLD:
                    self._state          = "CASCADE"
                    self._cascade_count += 1
                    evt = ReflexiveEvent(
                        ts_ns    = ts_ns,
                        kind     = "CASCADE",
                        rho      = round(self._rho, 4),
                        momentum = round(self._momentum, 4),
                        magnitude= round(abs(self._momentum), 4),
                    )
                    self._events.append(evt)
                elif self._momentum < self._CORRECTION_THRESHOLD:
                    self._state              = "CORRECTION"
                    self._correction_count  += 1
                    # Correction collapses momentum
                    self._momentum *= 0.3
                    evt = ReflexiveEvent(
                        ts_ns    = ts_ns,
                        kind     = "CORRECTION",
                        rho      = round(self._rho, 4),
                        momentum = round(self._momentum, 4),
                        magnitude= round(abs(self._momentum), 4),
                    )
                    self._events.append(evt)
                else:
                    self._state = "EQUILIBRIUM"
        except Exception:
            pass

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            rho_hist = list(self._rho_history)
            events   = [dataclasses.asdict(e) for e in list(self._events)[-20:]]
            return {
                "rho":              round(self._rho,       4),
                "sentiment":        round(self._sentiment, 4),
                "momentum":         round(self._momentum,  4),
                "state":            self._state,
                "cascade_count":    self._cascade_count,
                "correction_count": self._correction_count,
                "tick_count":       self._tick_count,
                "rho_history":      rho_hist[-50:],
                "recent_events":    events,
            }


# ── Singleton ──────────────────────────────────────────────────────────────────

_singleton: ReflexiveSimulationEngine | None = None
_lock = threading.Lock()


def get_reflexive_engine() -> ReflexiveSimulationEngine:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = ReflexiveSimulationEngine()
    return _singleton


__all__ = ["ReflexiveSimulationEngine", "ReflexiveEvent", "get_reflexive_engine"]
