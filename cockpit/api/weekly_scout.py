"""Cockpit API — /weekly_scout endpoint.

Returns the weekly alpha scouting report: top trader archetypes,
emerging regime signals, and recommended strategy adjustments.
Read-only. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["WeeklyScoutReport", "WeeklyScoutProvider"]


@dataclass(frozen=True, slots=True)
class ArchetypeInsight:
    handle: str
    archetype: str
    credibility_score: float
    sentiment_bias: str


@dataclass(frozen=True, slots=True)
class WeeklyScoutReport:
    ts_ns: int
    week_start_ns: int
    week_end_ns: int
    top_archetypes: tuple[ArchetypeInsight, ...]
    dominant_regime: str
    regime_confidence: float
    recommended_adjustments: tuple[str, ...]
    new_source_count: int


class WeeklyScoutProvider:
    """Assembles WeeklyScoutReport from knowledge store + regime state."""

    def __init__(self, knowledge_store: Any, regime_state: Any) -> None:
        self._knowledge = knowledge_store
        self._regime = regime_state

    def get_report(self, ts_ns: int, week_start_ns: int, week_end_ns: int) -> WeeklyScoutReport:
        archetypes = self._knowledge.top_archetypes(
            since_ns=week_start_ns, until_ns=week_end_ns, limit=10
        )
        regime = self._regime.current()
        insights = tuple(
            ArchetypeInsight(
                handle=a.handle, archetype=a.archetype,
                credibility_score=a.credibility_score,
                sentiment_bias=a.behavior_summary.get("sentiment_bias", "neutral"),
            )
            for a in archetypes
        )
        recommendations = self._build_recommendations(regime, insights)
        new_sources = self._knowledge.new_source_count(
            since_ns=week_start_ns, until_ns=week_end_ns
        )
        return WeeklyScoutReport(
            ts_ns=ts_ns,
            week_start_ns=week_start_ns,
            week_end_ns=week_end_ns,
            top_archetypes=insights,
            dominant_regime=regime.regime,
            regime_confidence=regime.confidence,
            recommended_adjustments=recommendations,
            new_source_count=new_sources,
        )

    def _build_recommendations(
        self, regime: Any, insights: tuple[ArchetypeInsight, ...]
    ) -> tuple[str, ...]:
        recs: list[str] = []
        bullish = sum(1 for i in insights if i.sentiment_bias == "bullish")
        bearish = sum(1 for i in insights if i.sentiment_bias == "bearish")
        if bullish > bearish * 2:
            recs.append("Crowd sentiment strongly bullish — watch for crowding risk")
        if bearish > bullish * 2:
            recs.append("Crowd sentiment strongly bearish — potential contrarian opportunity")
        if regime.regime == "volatile":
            recs.append("Volatile regime: tighten position limits, widen slippage estimates")
        return tuple(recs)
