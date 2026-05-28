"""Cockpit widget — master parameter sliders."""

from __future__ import annotations

from typing import Any

from system.fast_risk_cache import get_risk_cache

__all__ = ["master_sliders_payload", "set_slider"]

_SLIDER_BOUNDS: dict[str, tuple[float, float]] = {
    "max_order_size_usd": (100.0, 1_000_000.0),
    "max_position_pct": (0.01, 1.0),
    "circuit_breaker_drawdown": (1.0, 50.0),
    "circuit_breaker_loss_pct": (0.5, 25.0),
}


def master_sliders_payload() -> dict[str, Any]:
    rc = get_risk_cache().get()
    return {
        "max_order_size_usd": rc.max_order_size_usd,
        "max_position_pct": rc.max_position_pct,
        "circuit_breaker_drawdown": rc.circuit_breaker_drawdown,
        "circuit_breaker_loss_pct": rc.circuit_breaker_loss_pct,
        "bounds": _SLIDER_BOUNDS,
        "version_id": rc.version_id,
    }


def set_slider(slider: str, value: float, operator_id: str) -> dict[str, Any]:
    if slider not in _SLIDER_BOUNDS:
        return {"accepted": False, "reason": f"Unknown slider {slider!r}"}
    lo, hi = _SLIDER_BOUNDS[slider]
    if not lo <= value <= hi:
        return {"accepted": False,
                "reason": f"Value {value} out of [{lo}, {hi}] for {slider!r}"}
    # cache.update(**kwargs) returns updated RiskConstraints
    get_risk_cache().update(**{slider: value})
    return {"accepted": True, "slider": slider, "value": value}
