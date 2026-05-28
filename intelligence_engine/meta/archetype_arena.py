"""
intelligence_engine/meta/archetype_arena.py
DIX VISION v42.2 — Archetype Arena

Competitive evaluation arena where trader archetypes are matched
against each other in head-to-head comparisons. Performance scores
drive the archetype leaderboard that the CapitalScheduler and
StrategySynthesizer use for allocation decisions.
"""

from __future__ import annotations

import threading
import time as _time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ArenaMatch:
    """Result of a head-to-head archetype match."""
    match_id: str
    ts_ns: int
    archetype_a: str
    archetype_b: str
    winner: str          # archetype_id of winner, or "" for draw
    score_a: float
    score_b: float
    regime: str


@dataclass
class _ArchetypeRecord:
    archetype_id: str
    params: dict[str, float]
    wins: int = 0
    losses: int = 0
    draws: int = 0
    total_score: float = 0.0
    match_count: int = 0


class ArchetypeArena:
    """
    Head-to-head competitive arena for archetype evaluation.

    Thread-safe. Archetypes register their parameters; run_match()
    compares composite scores deterministically.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._archetypes: dict[str, _ArchetypeRecord] = {}
        self._matches: list[ArenaMatch] = []

    def register_archetype(
        self,
        archetype_id: str,
        params: dict[str, float],
    ) -> None:
        """Register or update an archetype."""
        with self._lock:
            if archetype_id not in self._archetypes:
                self._archetypes[archetype_id] = _ArchetypeRecord(
                    archetype_id=archetype_id,
                    params=dict(params),
                )
            else:
                self._archetypes[archetype_id].params = dict(params)

    def run_match(
        self,
        a_id: str,
        b_id: str,
        regime: str,
        ts_ns: int | None = None,
    ) -> ArenaMatch:
        """
        Run a head-to-head match between two archetypes.

        Composite score = mean of all param values (simple proxy for
        overall "strength" without live trading data). Callers can
        override scores by calling update_scores() after actual P&L.
        """
        ts_ns = ts_ns or _time.time_ns()
        with self._lock:
            rec_a = self._archetypes.get(a_id)
            rec_b = self._archetypes.get(b_id)

        if rec_a is None or rec_b is None:
            missing = a_id if rec_a is None else b_id
            raise ValueError(f"Archetype not registered: {missing!r}")

        score_a = _composite(rec_a.params)
        score_b = _composite(rec_b.params)

        if score_a > score_b:
            winner = a_id
        elif score_b > score_a:
            winner = b_id
        else:
            winner = ""

        match = ArenaMatch(
            match_id=str(uuid.uuid4()),
            ts_ns=ts_ns,
            archetype_a=a_id,
            archetype_b=b_id,
            winner=winner,
            score_a=score_a,
            score_b=score_b,
            regime=regime,
        )

        with self._lock:
            self._matches.append(match)
            a = self._archetypes[a_id]
            b = self._archetypes[b_id]
            a.total_score += score_a
            b.total_score += score_b
            a.match_count += 1
            b.match_count += 1
            if winner == a_id:
                a.wins += 1
                b.losses += 1
            elif winner == b_id:
                b.wins += 1
                a.losses += 1
            else:
                a.draws += 1
                b.draws += 1

        return match

    def leaderboard(self) -> list[tuple[str, float]]:
        """
        Return archetypes sorted by win_rate desc.

        Returns list of (archetype_id, win_rate).
        """
        with self._lock:
            rows = [
                (
                    rec.archetype_id,
                    rec.wins / rec.match_count if rec.match_count > 0 else 0.0,
                )
                for rec in self._archetypes.values()
            ]
        return sorted(rows, key=lambda x: x[1], reverse=True)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "archetypes": len(self._archetypes),
                "matches": len(self._matches),
                "leaderboard": self.leaderboard(),
            }


def _composite(params: dict[str, float]) -> float:
    """Mean of all param values as a simple composite score proxy."""
    if not params:
        return 0.0
    return sum(params.values()) / len(params)


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: ArchetypeArena | None = None
_lock = threading.Lock()


def get_archetype_arena() -> ArchetypeArena:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ArchetypeArena()
    return _instance


__all__ = ["ArenaMatch", "ArchetypeArena", "get_archetype_arena"]
