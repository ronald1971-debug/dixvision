"""Cockpit widget — master parameter sliders.

UI data model for the master-level parameter override sliders:
risk budget, position size multiplier, execution urgency.
B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["MasterSliders", "MasterSlidersWidget"]

_SLIDER_BOUNDS: dict[str, tuple[float, float]] = {
    "risk_budget_multiplier": (0.0, 2.0),
    "position_size_multiplier": (0.0, 2.0),
    "execution_urgency": (0.0, 1.0),
    "max_drawdown_override_pct": (1.0, 50.0),
    "confidence_threshold": (0.1, 1.0),
}


@dataclass(frozen=True, slots=True)
class MasterSliders:
    risk_budget_multiplier: float
    position_size_multiplier: float
    execution_urgency: float
    max_drawdown_override_pct: float
    confidence_threshold: float
    last_updated_ns: int
    updated_by: str


class MasterSlidersWidget:
    """Read/write interface for master slider UI panel."""

    def __init__(self, param_store: Any) -> None:
        self._store = param_store

    def get(self) -> MasterSliders:
        return self._store.get_master_sliders()

    def set_slider(
        self, slider: str, value: float, operator_id: str, ts_ns: int
    ) -> dict[str, Any]:
        if slider not in _SLIDER_BOUNDS:
            return {"accepted": False, "reason": f"Unknown slider: {slider!r}"}
        lo, hi = _SLIDER_BOUNDS[slider]
        if not lo <= value <= hi:
            return {"accepted": False,
                    "reason": f"Value {value} out of range [{lo}, {hi}] for {slider!r}"}
        self._store.set_slider(slider, value, operator_id=operator_id, ts_ns=ts_ns)
        return {"accepted": True, "reason": ""}

    def bounds(self) -> dict[str, tuple[float, float]]:
        return dict(_SLIDER_BOUNDS)
