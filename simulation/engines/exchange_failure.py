"""simulation.engines.exchange_failure — Exchange Failure Engine (Stage 8).

Simulates multi-venue exchange disruption and recovery:

  Venues: VENUE_A, VENUE_B, VENUE_C, VENUE_D, VENUE_E
  States: NORMAL → DEGRADED → CIRCUIT_BREAKER → PARTIAL_OUTAGE → FULL_OUTAGE
  Recovery: exponential mean time to recovery per state

Per-state characteristics:
  NORMAL           fill_rate=1.00  slippage_mult=1.0  latency_mult=1.0
  DEGRADED         fill_rate=0.85  slippage_mult=1.5  latency_mult=2.0
  CIRCUIT_BREAKER  fill_rate=0.40  slippage_mult=3.0  latency_mult=5.0
  PARTIAL_OUTAGE   fill_rate=0.20  slippage_mult=6.0  latency_mult=10.0
  FULL_OUTAGE      fill_rate=0.00  slippage_mult=inf  latency_mult=inf

Routing: orders automatically rerouted to best available venue.
"""
from __future__ import annotations

import dataclasses
import random
import threading
from collections import deque
from typing import Any

_STATES = ["NORMAL", "DEGRADED", "CIRCUIT_BREAKER", "PARTIAL_OUTAGE", "FULL_OUTAGE"]

_STATE_PROPS: dict[str, dict] = {
    "NORMAL":          {"fill_rate": 1.00, "slippage_mult": 1.0,  "latency_mult": 1.0},
    "DEGRADED":        {"fill_rate": 0.85, "slippage_mult": 1.5,  "latency_mult": 2.0},
    "CIRCUIT_BREAKER": {"fill_rate": 0.40, "slippage_mult": 3.0,  "latency_mult": 5.0},
    "PARTIAL_OUTAGE":  {"fill_rate": 0.20, "slippage_mult": 6.0,  "latency_mult": 10.0},
    "FULL_OUTAGE":     {"fill_rate": 0.00, "slippage_mult": 20.0, "latency_mult": 100.0},
}

_VENUE_NAMES = ["VENUE_A", "VENUE_B", "VENUE_C", "VENUE_D", "VENUE_E"]

# Mean ticks to fail / recover (exponential distribution)
_FAILURE_RATE  = 0.005   # prob of degradation each tick (per venue)
_RECOVERY_RATE = 0.08    # prob of improvement each tick (per venue)


@dataclasses.dataclass(frozen=True, slots=True)
class VenueState:
    venue:         str
    state:         str
    fill_rate:     float
    slippage_mult: float
    latency_mult:  float
    outage_ticks:  int


@dataclasses.dataclass(frozen=True, slots=True)
class ExchangeEvent:
    ts_ns:  int
    venue:  str
    kind:   str    # DEGRADED | CIRCUIT_BREAKER | OUTAGE | RECOVERED
    state:  str


class ExchangeFailureEngine:
    """Multi-venue failure simulation with routing and recovery."""

    def __init__(self, seed: int = 17) -> None:
        self._rng          = random.Random(seed)
        self._venue_states: dict[str, int] = {v: 0 for v in _VENUE_NAMES}
        self._outage_ticks: dict[str, int] = {v: 0 for v in _VENUE_NAMES}
        self._events: deque[ExchangeEvent] = deque(maxlen=200)
        self._failure_count   = 0
        self._recovery_count  = 0
        self._tick_count      = 0
        self._lock            = threading.Lock()

    # ------------------------------------------------------------------
    def tick(self, ts_ns: int) -> None:
        try:
            with self._lock:
                self._tick_count += 1
                for venue in _VENUE_NAMES:
                    state_idx = self._venue_states[venue]
                    prev_state = _STATES[state_idx]

                    if state_idx > 0:
                        self._outage_ticks[venue] += 1

                    # Random failure: step up state (worse)
                    if state_idx < 4 and self._rng.random() < _FAILURE_RATE:
                        state_idx = min(4, state_idx + 1)
                        new_state = _STATES[state_idx]
                        self._failure_count += 1
                        kind = {
                            1: "DEGRADED", 2: "CIRCUIT_BREAKER",
                            3: "PARTIAL_OUTAGE", 4: "FULL_OUTAGE",
                        }.get(state_idx, "DEGRADED")
                        self._events.append(ExchangeEvent(
                            ts_ns=ts_ns, venue=venue, kind=kind, state=new_state,
                        ))

                    # Recovery: step down state (better)
                    elif state_idx > 0 and self._rng.random() < _RECOVERY_RATE:
                        state_idx = max(0, state_idx - 1)
                        new_state = _STATES[state_idx]
                        self._recovery_count += 1
                        if state_idx == 0:
                            self._outage_ticks[venue] = 0
                        self._events.append(ExchangeEvent(
                            ts_ns=ts_ns, venue=venue, kind="RECOVERED", state=new_state,
                        ))

                    self._venue_states[venue] = state_idx
        except Exception:
            pass

    def best_venue(self) -> str:
        with self._lock:
            return min(
                _VENUE_NAMES,
                key=lambda v: self._venue_states[v],
            )

    def aggregate_fill_rate(self) -> float:
        """Weighted average fill rate across all venues."""
        with self._lock:
            rates = [
                _STATE_PROPS[_STATES[self._venue_states[v]]]["fill_rate"]
                for v in _VENUE_NAMES
            ]
        return round(sum(rates) / len(rates), 4)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            venue_list = [
                dataclasses.asdict(VenueState(
                    venue         = v,
                    state         = _STATES[self._venue_states[v]],
                    fill_rate     = _STATE_PROPS[_STATES[self._venue_states[v]]]["fill_rate"],
                    slippage_mult = _STATE_PROPS[_STATES[self._venue_states[v]]]["slippage_mult"],
                    latency_mult  = _STATE_PROPS[_STATES[self._venue_states[v]]]["latency_mult"],
                    outage_ticks  = self._outage_ticks[v],
                ))
                for v in _VENUE_NAMES
            ]
            events = [dataclasses.asdict(e) for e in list(self._events)[-20:]]
            failing = sum(1 for v in _VENUE_NAMES if self._venue_states[v] > 0)
            fill_r  = sum(
                _STATE_PROPS[_STATES[self._venue_states[v]]]["fill_rate"]
                for v in _VENUE_NAMES
            ) / len(_VENUE_NAMES)
            return {
                "tick_count":        self._tick_count,
                "failure_count":     self._failure_count,
                "recovery_count":    self._recovery_count,
                "venues_failing":    failing,
                "aggregate_fill_rate": round(fill_r, 4),
                "best_venue":        self.best_venue(),
                "venues":            venue_list,
                "recent_events":     events,
            }


# ── Singleton ──────────────────────────────────────────────────────────────────

_singleton: ExchangeFailureEngine | None = None
_lock = threading.Lock()


def get_exchange_failure_engine() -> ExchangeFailureEngine:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = ExchangeFailureEngine()
    return _singleton


__all__ = ["ExchangeFailureEngine", "VenueState", "ExchangeEvent",
           "get_exchange_failure_engine"]
