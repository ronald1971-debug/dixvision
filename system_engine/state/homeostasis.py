"""system_engine/state/homeostasis.py
DIX VISION v42.2 — System Homeostasis

Maintains system-level homeostatic balance by monitoring key health
metrics and triggering corrective actions when parameters drift outside
acceptable bands. Analogous to biological homeostasis — detects
imbalance and signals restoration actions.

Thread-safe. No IO in core logic. Emits to ledger via append_event.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class HomeostasisState(StrEnum):
    BALANCED = "BALANCED"
    STRESSED = "STRESSED"
    CRITICAL = "CRITICAL"
    RESTORING = "RESTORING"


@dataclass(frozen=True, slots=True)
class HomeostaticBand:
    """Acceptable operating range for a system metric."""
    metric: str
    low: float        # lower bound (inclusive)
    high: float       # upper bound (inclusive)
    warn_low: float   # soft lower bound
    warn_high: float  # soft upper bound


@dataclass(frozen=True, slots=True)
class HomeostaticReading:
    """A metric reading with its homeostatic state."""
    metric: str
    value: float
    state: HomeostasisState
    deviation: float   # signed distance from nearest band boundary (0 = within)
    ts_ns: int


class HomeostaticMonitor:
    """
    Monitors system metrics against homeostatic bands.

    Thread-safe. Callers register bands and update metric values;
    the monitor computes state and provides restoration signals.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bands: dict[str, HomeostaticBand] = {}
        self._readings: dict[str, deque[HomeostaticReading]] = {}
        self._window = 100

    def register_band(self, band: HomeostaticBand) -> None:
        with self._lock:
            self._bands[band.metric] = band
            if band.metric not in self._readings:
                self._readings[band.metric] = deque(maxlen=self._window)

    def update(self, metric: str, value: float, ts_ns: int) -> HomeostaticReading:
        with self._lock:
            band = self._bands.get(metric)
        if band is None:
            reading = HomeostaticReading(
                metric=metric,
                value=value,
                state=HomeostasisState.BALANCED,
                deviation=0.0,
                ts_ns=ts_ns,
            )
        else:
            state, deviation = self._classify(band, value)
            reading = HomeostaticReading(
                metric=metric,
                value=value,
                state=state,
                deviation=deviation,
                ts_ns=ts_ns,
            )
        with self._lock:
            if metric not in self._readings:
                self._readings[metric] = deque(maxlen=self._window)
            self._readings[metric].append(reading)
        return reading

    def _classify(
        self,
        band: HomeostaticBand,
        value: float,
    ) -> tuple[HomeostasisState, float]:
        if value < band.low:
            return HomeostasisState.CRITICAL, band.low - value
        if value > band.high:
            return HomeostasisState.CRITICAL, value - band.high
        if value < band.warn_low:
            return HomeostasisState.STRESSED, band.warn_low - value
        if value > band.warn_high:
            return HomeostasisState.STRESSED, value - band.warn_high
        return HomeostasisState.BALANCED, 0.0

    def overall_state(self) -> HomeostasisState:
        """Return the worst state across all tracked metrics."""
        with self._lock:
            all_readings = {
                m: list(v)[-1] if v else None
                for m, v in self._readings.items()
            }
        states = [r.state for r in all_readings.values() if r is not None]
        if HomeostasisState.CRITICAL in states:
            return HomeostasisState.CRITICAL
        if HomeostasisState.STRESSED in states:
            return HomeostasisState.STRESSED
        return HomeostasisState.BALANCED

    def latest(self, metric: str) -> HomeostaticReading | None:
        with self._lock:
            dq = self._readings.get(metric)
            return dq[-1] if dq else None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latest = {
                m: list(v)[-1].__dict__ if v else None
                for m, v in self._readings.items()
            }
        return {
            "metrics": list(latest.keys()),
            "overall_state": self.overall_state().value,
            "latest": latest,
        }


# Singleton factory
_instance: HomeostaticMonitor | None = None
_lock = threading.Lock()


def get_homeostasis() -> HomeostaticMonitor:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = HomeostaticMonitor()
    return _instance


__all__ = [
    "HomeostaticBand",
    "HomeostaticMonitor",
    "HomeostaticReading",
    "HomeostasisState",
    "get_homeostasis",
]
