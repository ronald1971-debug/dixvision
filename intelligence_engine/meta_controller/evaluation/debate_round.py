"""
intelligence_engine/meta_controller/evaluation/debate_round.py
DIX VISION v42.2 — Debate Round (meta-controller evaluation)

Structured debate between strategy agents to reach a consensus
direction before emitting an execution intent. Each agent submits a
DebatePosition (BUY / SELL / HOLD + confidence); the orchestrator
runs a confidence-weighted majority vote.

Distinct from intelligence_engine/agents/debate_round.py (agent-level
debate) — this operates at the meta-controller evaluation tier and
aggregates across multiple agent types.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

_BUY = "BUY"
_SELL = "SELL"
_HOLD = "HOLD"


@dataclass(frozen=True, slots=True)
class DebatePosition:
    """A single agent's position in a debate round."""
    agent_id: str
    direction: str       # BUY | SELL | HOLD
    confidence: float    # [0, 1]
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class DebateRound:
    """Result of a completed debate round."""
    round_id: str
    ts_ns: int
    positions: tuple[DebatePosition, ...]
    consensus_direction: str
    consensus_confidence: float
    dissent_count: int
    detail: str = ""


class DebateOrchestrator:
    """
    Runs debate rounds via confidence-weighted majority vote.

    Pure — no state is mutated; each run_round() call is independent.
    """

    def run_round(
        self,
        positions: list[DebatePosition],
        ts_ns: int,
    ) -> DebateRound:
        """
        Execute one debate round.

        Confidence-weighted vote:
          score(direction) = sum of confidence for all positions in that direction
        Winner = direction with highest score; ties → HOLD.
        consensus_confidence = winner_score / total_weight.
        dissent_count = positions that voted against the winner.
        """
        if not positions:
            return DebateRound(
                round_id=str(uuid.uuid4()),
                ts_ns=ts_ns,
                positions=(),
                consensus_direction=_HOLD,
                consensus_confidence=0.0,
                dissent_count=0,
                detail="no_positions",
            )

        scores: dict[str, float] = {_BUY: 0.0, _SELL: 0.0, _HOLD: 0.0}
        total_weight = 0.0
        for pos in positions:
            d = pos.direction.upper()
            if d not in scores:
                d = _HOLD
            scores[d] += pos.confidence
            total_weight += pos.confidence

        if total_weight <= 0:
            direction = _HOLD
            conf = 0.0
        else:
            best_dir = max(scores, key=lambda d: scores[d])
            best_score = scores[best_dir]
            # Check for tie between BUY and SELL
            sorted_scores = sorted(scores.values(), reverse=True)
            if len(sorted_scores) >= 2 and sorted_scores[0] == sorted_scores[1]:
                direction = _HOLD
                conf = 0.0
            else:
                direction = best_dir
                conf = best_score / total_weight

        dissent = sum(
            1 for p in positions
            if p.direction.upper() != direction
        )

        return DebateRound(
            round_id=str(uuid.uuid4()),
            ts_ns=ts_ns,
            positions=tuple(positions),
            consensus_direction=direction,
            consensus_confidence=conf,
            dissent_count=dissent,
            detail=f"n_agents={len(positions)} scores={scores}",
        )


__all__ = ["DebatePosition", "DebateRound", "DebateOrchestrator"]
