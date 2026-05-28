"""Imitation engine (BUILD-DIRECTIVE §15 — TIS module 14).

Simulates what a specific trader WOULD do given the current market state.
Used by Indira to:
1. Compare her decision to what legendary traders would do
2. Generate learning signal from divergence
3. Build meta-learning: "PTJ would have cut here, I held — was I right?"

The imitation engine does NOT execute trades. It produces hypothetical
ExecutionDecisions for comparison/learning only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ImitationAction(StrEnum):
    """Action a simulated trader would take."""

    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"
    CUT_LOSS = "CUT_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    SCALE_IN = "SCALE_IN"
    SCALE_OUT = "SCALE_OUT"


@dataclass(frozen=True, slots=True)
class ImitatedDecision:
    """What a simulated trader would do in current conditions."""

    trader_id: str
    action: ImitationAction
    conviction: float  # 0=unsure, 1=maximum conviction
    rationale: str
    relevant_atoms: tuple[str, ...]  # which strategy atoms drive this
    regime_context: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class DivergenceSignal:
    """Divergence between Indira's decision and a simulated trader."""

    trader_id: str
    indira_action: str
    trader_action: str
    divergence_magnitude: float  # 0=same, 1=opposite
    learning_value: float  # how much to learn from this divergence
    ts_ns: int


class ImitationEngine:
    """Simulates trader decisions for comparison and learning.

    For each tracked trader, the engine maintains a model of their
    decision logic (derived from their atoms + philosophy). Given
    market state, it produces what they WOULD do.
    """

    def __init__(self) -> None:
        self._trader_models: dict[str, dict[str, Any]] = {}

    def register_trader_model(
        self,
        *,
        trader_id: str,
        philosophy: str,
        risk_tolerance: float,
        preferred_regimes: list[str],
        entry_bias: float,  # -1=contrarian, +1=momentum
        exit_discipline: float,  # 0=loose, 1=strict
        atoms: list[str] | None = None,
    ) -> None:
        """Register a trader model for imitation."""
        self._trader_models[trader_id] = {
            "philosophy": philosophy,
            "risk_tolerance": risk_tolerance,
            "preferred_regimes": preferred_regimes,
            "entry_bias": entry_bias,
            "exit_discipline": exit_discipline,
            "atoms": atoms or [],
        }

    def simulate(
        self,
        *,
        trader_id: str,
        market_regime: str,
        trend_strength: float,
        volatility: float,
        position_pnl: float,
        ts_ns: int,
    ) -> ImitatedDecision | None:
        """Simulate what a trader would do given current state."""
        model = self._trader_models.get(trader_id)
        if model is None:
            return None

        risk_tolerance = model["risk_tolerance"]
        entry_bias = model["entry_bias"]
        exit_discipline = model["exit_discipline"]
        preferred = model["preferred_regimes"]

        # Regime alignment check
        in_preferred_regime = market_regime in preferred if preferred else True

        # Decision logic based on trader model
        action = ImitationAction.HOLD
        conviction = 0.3
        rationale = "No clear signal"

        # Entry logic: momentum traders buy strength, contrarians buy weakness
        if position_pnl == 0.0:  # no position
            if entry_bias > 0 and trend_strength > 0.5:
                action = ImitationAction.BUY
                conviction = min(trend_strength * entry_bias, 1.0)
                rationale = "Momentum entry on trend strength"
            elif entry_bias < 0 and trend_strength < -0.3:
                action = ImitationAction.BUY
                conviction = min(abs(trend_strength) * abs(entry_bias), 1.0)
                rationale = "Contrarian entry on oversold"
        else:
            # Exit logic: strict traders cut early, loose traders hold longer
            if position_pnl < -0.02 * risk_tolerance:
                action = ImitationAction.CUT_LOSS
                conviction = exit_discipline
                rationale = "Loss exceeds tolerance"
            elif position_pnl > 0.05 and exit_discipline > 0.7:
                action = ImitationAction.TAKE_PROFIT
                conviction = 0.6
                rationale = "Disciplined profit taking"

        # Volatility adjustment
        if volatility > 2.0 and not in_preferred_regime:
            if action in (ImitationAction.BUY, ImitationAction.STRONG_BUY):
                action = ImitationAction.HOLD
                conviction *= 0.5
                rationale = "High vol outside preferred regime — standing aside"

        return ImitatedDecision(
            trader_id=trader_id,
            action=action,
            conviction=conviction,
            rationale=rationale,
            relevant_atoms=tuple(model.get("atoms", [])[:3]),
            regime_context=market_regime,
            ts_ns=ts_ns,
        )

    def compute_divergence(
        self,
        *,
        indira_action: str,
        imitated: ImitatedDecision,
        ts_ns: int,
    ) -> DivergenceSignal:
        """Compute divergence between Indira and a simulated trader."""
        # Action distance mapping
        action_values = {
            "STRONG_BUY": 2.0,
            "BUY": 1.0,
            "SCALE_IN": 0.8,
            "HOLD": 0.0,
            "SCALE_OUT": -0.5,
            "SELL": -1.0,
            "STRONG_SELL": -2.0,
            "CUT_LOSS": -1.5,
            "TAKE_PROFIT": -0.7,
        }
        indira_val = action_values.get(indira_action, 0.0)
        trader_val = action_values.get(imitated.action.value, 0.0)

        magnitude = abs(indira_val - trader_val) / 4.0  # normalize to 0-1
        # Learning value: higher when the trader is highly convicted
        learning_value = magnitude * imitated.conviction

        return DivergenceSignal(
            trader_id=imitated.trader_id,
            indira_action=indira_action,
            trader_action=imitated.action.value,
            divergence_magnitude=min(magnitude, 1.0),
            learning_value=min(learning_value, 1.0),
            ts_ns=ts_ns,
        )

    @property
    def model_count(self) -> int:
        """Number of registered trader models."""
        return len(self._trader_models)
