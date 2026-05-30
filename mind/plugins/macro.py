"""mind.plugins.macro — Macro Intelligence Plugin.

Processes macroeconomic signals: central bank decisions, CPI/NFP/GDP releases,
yield curve changes, and geopolitical events. Outputs regime-aware MacroSignal
into the intelligence pipeline.

Uses the canonical normalizer output and respects trust ≤ 0.5 for external
sources. Integrates with the regime router for macro regime detection.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from system import time_source


class MacroRegime(StrEnum):
    """Current macro environment classification."""

    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    TRANSITION = "TRANSITION"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LIQUIDITY_CRISIS = "LIQUIDITY_CRISIS"


class MacroEventType(StrEnum):
    """Types of macro events processed."""

    INTEREST_RATE = "INTEREST_RATE"
    CPI = "CPI"
    GDP = "GDP"
    NFP = "NFP"
    CENTRAL_BANK = "CENTRAL_BANK"
    GEOPOLITICAL = "GEOPOLITICAL"
    YIELD_CURVE = "YIELD_CURVE"


@dataclass(frozen=True, slots=True)
class MacroSignal:
    """Output from macro intelligence analysis."""

    regime: MacroRegime
    event_type: MacroEventType
    impact_score: float
    confidence: float
    direction_bias: str
    source: str
    ts_ns: int = field(default_factory=time_source.wall_ns)


class MacroPlugin:
    """Intelligence plugin for macroeconomic regime analysis.

    Processes macro events, maintains regime state, and outputs
    bias signals for the meta-controller's allocation weighting.
    """

    __slots__ = ("_current_regime", "_events", "_lock", "_window_size", "_active")

    def __init__(self, window_size: int = 50) -> None:
        self._current_regime = MacroRegime.RISK_ON
        self._events: list[MacroSignal] = []
        self._lock = threading.Lock()
        self._window_size = window_size
        self._active = True

    @property
    def active(self) -> bool:
        return self._active

    @property
    def current_regime(self) -> MacroRegime:
        return self._current_regime

    def process(self, normalized_payload: dict[str, Any]) -> MacroSignal | None:
        """Process a normalized macro event payload.

        Args:
            normalized_payload: Canonical normalizer output.

        Returns:
            MacroSignal if significant, None if noise.
        """
        if not self._active:
            return None

        event_type_str = normalized_payload.get("event_type", "")
        try:
            event_type = MacroEventType(event_type_str)
        except ValueError:
            return None

        impact = float(normalized_payload.get("impact_score", 0.0))
        if impact < 0.2:
            return None

        trust = float(normalized_payload.get("trust_score", 0.3))
        confidence = min(trust * impact, 0.5)

        direction = self._assess_direction(event_type, normalized_payload)
        regime = self._classify_regime(event_type, impact, normalized_payload)

        signal = MacroSignal(
            regime=regime,
            event_type=event_type,
            impact_score=impact,
            confidence=confidence,
            direction_bias=direction,
            source=normalized_payload.get("source_platform", "macro"),
        )

        with self._lock:
            self._events.append(signal)
            if len(self._events) > self._window_size:
                self._events = self._events[-self._window_size :]
            self._current_regime = regime

        return signal

    def _assess_direction(self, event_type: MacroEventType, payload: dict[str, Any]) -> str:
        """Assess directional bias from a macro event."""
        actual = float(payload.get("actual", 0))
        expected = float(payload.get("expected", 0))
        if actual > expected:
            return "bullish" if event_type != MacroEventType.CPI else "bearish"
        elif actual < expected:
            return "bearish" if event_type != MacroEventType.CPI else "bullish"
        return "neutral"

    def _classify_regime(
        self, event_type: MacroEventType, impact: float, payload: dict[str, Any]
    ) -> MacroRegime:
        """Classify current macro regime based on recent events."""
        if impact > 0.8 and event_type == MacroEventType.GEOPOLITICAL:
            return MacroRegime.HIGH_VOLATILITY
        if event_type == MacroEventType.INTEREST_RATE:
            change = float(payload.get("change_bps", 0))
            if abs(change) > 50:
                return MacroRegime.TRANSITION
        if len(self._events) >= 3:
            recent_impacts = [e.impact_score for e in self._events[-3:]]
            if all(i > 0.6 for i in recent_impacts):
                return MacroRegime.HIGH_VOLATILITY
        return self._current_regime


__all__ = [
    "MacroEventType",
    "MacroPlugin",
    "MacroRegime",
    "MacroSignal",
]
