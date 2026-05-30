"""simulation.engines.crowd_psychology — Crowd Psychology Engine (Stage 8).

7-state sentiment machine with herding and social contagion:

  EUPHORIA ←→ OVERCONFIDENT ←→ BULLISH ←→ NEUTRAL ←→ BEARISH ←→ PANIC ←→ CAPITULATION

Herding coefficient h ∈ [0, 1]: fraction of neutral agents that adopt the
dominant sentiment each tick. High h → rapid crowd polarisation.

Social contagion: sentiment spreads via a network diffusion model.
  Each tick: neutral_proportion × h → join dominant camp
  At sentiment extremes (EUPHORIA / CAPITULATION): contrarian signal fires.
"""
from __future__ import annotations

import dataclasses
import random
import threading
from collections import deque
from typing import Any

_STATES = [
    "CAPITULATION",
    "PANIC",
    "BEARISH",
    "NEUTRAL",
    "BULLISH",
    "OVERCONFIDENT",
    "EUPHORIA",
]


@dataclasses.dataclass(frozen=True, slots=True)
class CrowdEvent:
    ts_ns:          int
    kind:           str    # TRANSITION | HERDING_SURGE | CONTRARIAN_SIGNAL
    from_state:     str
    to_state:       str
    herding_coeff:  float


class CrowdPsychologyEngine:
    """Sentiment state machine with herding, contagion, and contrarian detection."""

    _CONTRARIAN_STATES = {"EUPHORIA", "CAPITULATION"}
    _EXTREME_STATES    = {"EUPHORIA", "CAPITULATION", "PANIC"}

    def __init__(self, seed: int = 55) -> None:
        self._state_idx      = 3         # start NEUTRAL
        self._herding_coeff  = 0.25      # base herding
        self._fear_greed     = 50.0      # 0=fear, 100=greed
        self._contrarian_signals = 0
        self._herding_surges     = 0
        self._transitions        = 0
        self._tick_count         = 0
        self._rng                = random.Random(seed)
        self._events: deque[CrowdEvent]       = deque(maxlen=200)
        self._fg_history: deque[float]        = deque(maxlen=200)
        self._herding_history: deque[float]   = deque(maxlen=200)
        self._lock               = threading.Lock()

    # ------------------------------------------------------------------
    def tick(self, ts_ns: int, price_return: float = 0.0,
             market_vol: float = 0.02) -> None:
        try:
            with self._lock:
                self._tick_count += 1
                prev_state = _STATES[self._state_idx]

                # Price return → sentiment pressure
                pressure = price_return * 15.0
                noise    = self._rng.gauss(0.0, 0.5)

                # Herding amplifies pressure in extreme states
                h = self._herding_coeff
                if self._state_idx in {0, 1, 5, 6}:
                    h = min(0.90, h + 0.10)

                amplified_pressure = pressure * (1.0 + h) + noise

                # State transition logic
                state_float = self._state_idx + amplified_pressure
                state_float = max(0.0, min(6.0, state_float))
                new_state_idx = round(state_float)

                # Fear & greed index tracks state
                self._fear_greed = max(0.0, min(100.0,
                    self._fear_greed + amplified_pressure * 5.0
                    + self._rng.gauss(0.0, 1.0)
                ))

                # Herding coefficient adapts: stronger in extremes
                vol_boost = market_vol / 0.02
                self._herding_coeff = max(0.05, min(0.95,
                    self._herding_coeff + (vol_boost - 1.0) * 0.01
                    + self._rng.gauss(0.0, 0.01)
                ))

                self._herding_history.append(round(self._herding_coeff, 4))
                self._fg_history.append(round(self._fear_greed, 2))

                # Fire events
                new_state = _STATES[new_state_idx]

                if new_state_idx != self._state_idx:
                    self._transitions += 1
                    self._events.append(CrowdEvent(
                        ts_ns         = ts_ns,
                        kind          = "TRANSITION",
                        from_state    = prev_state,
                        to_state      = new_state,
                        herding_coeff = round(self._herding_coeff, 4),
                    ))
                    self._state_idx = new_state_idx

                if h > 0.70:
                    self._herding_surges += 1
                    self._events.append(CrowdEvent(
                        ts_ns         = ts_ns,
                        kind          = "HERDING_SURGE",
                        from_state    = new_state,
                        to_state      = new_state,
                        herding_coeff = round(h, 4),
                    ))

                if new_state in self._CONTRARIAN_STATES and self._rng.random() < 0.15:
                    self._contrarian_signals += 1
                    self._events.append(CrowdEvent(
                        ts_ns         = ts_ns,
                        kind          = "CONTRARIAN_SIGNAL",
                        from_state    = new_state,
                        to_state      = new_state,
                        herding_coeff = round(self._herding_coeff, 4),
                    ))
        except Exception:
            pass

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            events   = [dataclasses.asdict(e) for e in list(self._events)[-20:]]
            fg_hist  = list(self._fg_history)[-50:]
            h_hist   = list(self._herding_history)[-50:]
            return {
                "state":               _STATES[self._state_idx],
                "state_idx":           self._state_idx,
                "fear_greed":          round(self._fear_greed, 2),
                "herding_coeff":       round(self._herding_coeff, 4),
                "contrarian_signals":  self._contrarian_signals,
                "herding_surges":      self._herding_surges,
                "transitions":         self._transitions,
                "tick_count":          self._tick_count,
                "fear_greed_history":  fg_hist,
                "herding_history":     h_hist,
                "recent_events":       events,
                "all_states":          _STATES,
            }


# ── Singleton ──────────────────────────────────────────────────────────────────

_singleton: CrowdPsychologyEngine | None = None
_lock = threading.Lock()


def get_crowd_psychology_engine() -> CrowdPsychologyEngine:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = CrowdPsychologyEngine()
    return _singleton


__all__ = ["CrowdPsychologyEngine", "CrowdEvent", "get_crowd_psychology_engine"]
