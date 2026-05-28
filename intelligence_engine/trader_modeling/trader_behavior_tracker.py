"""Trader behavior tracker (BUILD-DIRECTIVE §15 — TIS module 8).

Tracks trader behavior patterns over time: consistency, adaptability,
regime switching, and execution discipline. This feeds the credibility
engine and the meta-controller's allocation weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BehaviorSnapshot:
    """Point-in-time behavioral measurement."""

    trader_id: str
    ts_ns: int
    consistency_score: float  # 0=erratic, 1=perfectly consistent
    adaptability_score: float  # 0=rigid, 1=highly adaptive
    discipline_score: float  # 0=impulsive, 1=fully disciplined
    regime_alignment: float  # how well trader adapts to regime
    active_regimes: tuple[str, ...]
    recent_decisions: int
    recent_correct: int


class TraderBehaviorTracker:
    """Tracks and scores trader behavior over time.

    Behavior tracking enables:
    1. Credibility decay/boost based on recent performance
    2. Meta-controller allocation weighting
    3. Regime-specific trust scoring
    4. Imitation confidence calibration
    """

    def __init__(self, *, window_size: int = 100) -> None:
        self._window_size = window_size
        self._histories: dict[str, list[dict[str, Any]]] = {}

    def record_decision(
        self,
        *,
        trader_id: str,
        ts_ns: int,
        regime: str,
        decision_type: str,
        outcome: float,  # positive = correct, negative = wrong
        was_disciplined: bool = True,
    ) -> None:
        """Record a trader decision outcome."""
        history = self._histories.setdefault(trader_id, [])
        history.append(
            {
                "ts_ns": ts_ns,
                "regime": regime,
                "decision_type": decision_type,
                "outcome": outcome,
                "disciplined": was_disciplined,
            }
        )
        # Trim to window
        if len(history) > self._window_size:
            self._histories[trader_id] = history[-self._window_size :]

    def snapshot(self, trader_id: str, *, ts_ns: int = 0) -> BehaviorSnapshot:
        """Get current behavioral snapshot for a trader."""
        history = self._histories.get(trader_id, [])
        if not history:
            return BehaviorSnapshot(
                trader_id=trader_id,
                ts_ns=ts_ns,
                consistency_score=0.5,
                adaptability_score=0.5,
                discipline_score=0.5,
                regime_alignment=0.5,
                active_regimes=(),
                recent_decisions=0,
                recent_correct=0,
            )

        # Consistency: how stable are outcomes?
        outcomes = [h["outcome"] for h in history]
        positive_count = sum(1 for o in outcomes if o > 0)
        total = len(outcomes)
        consistency = positive_count / max(total, 1)

        # Discipline score
        disciplined_count = sum(1 for h in history if h.get("disciplined", True))
        discipline = disciplined_count / max(total, 1)

        # Active regimes
        regimes = list({h["regime"] for h in history[-20:]})

        # Regime alignment: are outcomes better in specific regimes?
        regime_outcomes: dict[str, list[float]] = {}
        for h in history:
            regime_outcomes.setdefault(h["regime"], []).append(h["outcome"])
        best_regime_score = 0.0
        for regime_o in regime_outcomes.values():
            if regime_o:
                score = sum(1 for o in regime_o if o > 0) / len(regime_o)
                best_regime_score = max(best_regime_score, score)

        # Adaptability: can trader switch regimes successfully?
        if len(regimes) >= 3:
            adaptability = min(len(regimes) / 5.0, 1.0)
        else:
            adaptability = 0.3

        return BehaviorSnapshot(
            trader_id=trader_id,
            ts_ns=ts_ns,
            consistency_score=consistency,
            adaptability_score=adaptability,
            discipline_score=discipline,
            regime_alignment=best_regime_score,
            active_regimes=tuple(regimes),
            recent_decisions=total,
            recent_correct=positive_count,
        )

    def get_regime_specialists(self, regime: str, *, top_n: int = 5) -> list[str]:
        """Get traders who perform best in a specific regime."""
        scores: list[tuple[str, float]] = []
        for trader_id, history in self._histories.items():
            regime_outcomes = [h["outcome"] for h in history if h["regime"] == regime]
            if len(regime_outcomes) >= 5:
                score = sum(1 for o in regime_outcomes if o > 0) / len(regime_outcomes)
                scores.append((trader_id, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in scores[:top_n]]
