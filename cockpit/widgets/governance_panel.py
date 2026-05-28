"""Cockpit widget — governance panel.

Displays pending patch proposals, trust scores, and triple-window
dry-run results for operator review. Read-only. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["PatchProposalRow", "GovernancePanelState", "GovernancePanelWidget"]


@dataclass(frozen=True, slots=True)
class PatchProposalRow:
    intent_id: str
    strategy_id: str
    parameter: str
    old_value: Any
    new_value: Any
    reason: str
    pipeline_stage: str   # "PROPOSED" | "VALIDATED" | "DRY_RUN" | "APPROVED" | "REJECTED"
    dry_run_passed: bool
    ts_ns: int


@dataclass(frozen=True, slots=True)
class TrustRow:
    source_id: str
    score: float
    streak: int
    status: str    # "TRUSTED" | "PROBATION" | "SUSPENDED"


@dataclass(frozen=True, slots=True)
class GovernancePanelState:
    ts_ns: int
    pending_proposals: tuple[PatchProposalRow, ...]
    trust_scores: tuple[TrustRow, ...]
    proposals_awaiting_operator: int


class GovernancePanelWidget:
    """Read interface for governance panel rendering."""

    def __init__(self, patch_store: Any, trust_engine: Any) -> None:
        self._patches = patch_store
        self._trust = trust_engine

    def get_state(self, ts_ns: int) -> GovernancePanelState:
        proposals_raw = self._patches.pending()
        proposals = tuple(
            PatchProposalRow(
                intent_id=p.intent_id,
                strategy_id=p.strategy_id,
                parameter=p.parameter,
                old_value=p.old_value,
                new_value=p.new_value,
                reason=p.reason,
                pipeline_stage=p.stage,
                dry_run_passed=getattr(p, "dry_run_passed", False),
                ts_ns=p.ts_ns,
            )
            for p in proposals_raw
        )
        trust_rows = tuple(
            TrustRow(
                source_id=t.source_id,
                score=t.score,
                streak=t.streak,
                status=("TRUSTED" if t.score >= 0.7
                        else "PROBATION" if t.score >= 0.4
                        else "SUSPENDED"),
            )
            for t in self._trust.all_sources()
        )
        awaiting = sum(1 for p in proposals
                       if p.pipeline_stage in ("DRY_RUN", "VALIDATED"))
        return GovernancePanelState(
            ts_ns=ts_ns,
            pending_proposals=proposals,
            trust_scores=trust_rows,
            proposals_awaiting_operator=awaiting,
        )
