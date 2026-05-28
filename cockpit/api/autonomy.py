"""Cockpit API — /autonomy endpoint.

Returns current autonomy level, MetaController shadow policy state,
and fallback lane status. Read-only. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["AutonomySnapshot", "AutonomyProvider"]


@dataclass(frozen=True, slots=True)
class AutonomySnapshot:
    ts_ns: int
    autonomy_level: str       # "FULL" | "SUPERVISED" | "MANUAL"
    shadow_policy_active: bool
    shadow_consecutive_agree: int
    fallback_lane_active: bool
    fallback_budget_ns: int
    meta_controller_confidence: float


class AutonomyProvider:
    """Assembles AutonomySnapshot from MetaController state."""

    def __init__(self, meta_controller: Any) -> None:
        self._mc = meta_controller

    def get_snapshot(self, ts_ns: int) -> AutonomySnapshot:
        state = self._mc.current_state()
        return AutonomySnapshot(
            ts_ns=ts_ns,
            autonomy_level=state.autonomy_level,
            shadow_policy_active=state.shadow_active,
            shadow_consecutive_agree=state.shadow_consecutive_agree,
            fallback_lane_active=state.fallback_active,
            fallback_budget_ns=state.fallback_budget_ns,
            meta_controller_confidence=state.confidence,
        )
