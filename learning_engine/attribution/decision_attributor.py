"""DecisionAttributor — links outcomes to the decisions/signals that caused them.

For every trade outcome, traces back to:
- Which signal triggered the entry
- Which strategy produced the signal
- Which archetype the strategy instantiates
- Which regime conditions were active
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Attribution:
    """Full attribution chain for a trade outcome."""

    trade_id: str
    signal_id: str
    strategy_id: str
    archetype_id: str
    regime_at_entry: str
    regime_at_exit: str
    confidence_at_entry: float
    contribution_to_portfolio_bps: float
    was_profitable: bool
    attribution_chain: tuple[str, ...]  # ordered chain of causes


class DecisionAttributor:
    """Traces trade outcomes back to their causal decision chain.

    Maintains a registry of active decisions and links them to outcomes
    when trades close. Pure / stateful but deterministic (INV-15).
    """

    def __init__(self) -> None:
        self._pending: dict[str, dict[str, str | float]] = {}
        self._attributions: list[Attribution] = []

    def register_decision(
        self,
        *,
        trade_id: str,
        signal_id: str,
        strategy_id: str,
        archetype_id: str,
        regime: str,
        confidence: float,
    ) -> None:
        """Register a new trade entry for future attribution."""
        self._pending[trade_id] = {
            "signal_id": signal_id,
            "strategy_id": strategy_id,
            "archetype_id": archetype_id,
            "regime_at_entry": regime,
            "confidence": confidence,
        }

    def attribute(
        self,
        *,
        trade_id: str,
        pnl_bps: float,
        regime_at_exit: str,
        portfolio_contribution_bps: float,
    ) -> Attribution | None:
        """Attribute a closed trade to its decision chain."""
        entry = self._pending.pop(trade_id, None)
        if entry is None:
            return None

        chain = (
            str(entry["archetype_id"]),
            str(entry["strategy_id"]),
            str(entry["signal_id"]),
            trade_id,
        )

        attr = Attribution(
            trade_id=trade_id,
            signal_id=str(entry["signal_id"]),
            strategy_id=str(entry["strategy_id"]),
            archetype_id=str(entry["archetype_id"]),
            regime_at_entry=str(entry["regime_at_entry"]),
            regime_at_exit=regime_at_exit,
            confidence_at_entry=float(entry["confidence"]),
            contribution_to_portfolio_bps=portfolio_contribution_bps,
            was_profitable=pnl_bps > 0,
            attribution_chain=chain,
        )
        self._attributions.append(attr)
        return attr

    @property
    def history(self) -> list[Attribution]:
        return list(self._attributions)
