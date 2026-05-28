"""
cognitive_governance/hallucination_guard.py
DIX VISION v42.2 — Hallucination Guard

Detects self-referential inference loops: the pathological state where
the system's own predictions become the inputs to its own reward or
learning update signals without any external truth anchor breaking
the loop.

The guard tracks a "self-reference depth" counter per learning signal:
  depth=0  → signal is grounded in a real external observation
  depth=1  → signal references a prediction that was grounded (OK)
  depth=2  → signal references a prediction of a prediction (WARNING)
  depth≥3  → signal is purely self-referential (CRITICAL)

Additionally detects PAPER_LOOP: signals tagged as coming from paper/
simulation mode that are feeding the same learning loop as live signals.
This is a special form of hallucination because the system trains on
fills that never happened.
"""

from __future__ import annotations

import threading
import time as _time

from core.contracts.cognitive_governance import (
    CognitiveSeverity,
    CognitiveViolationKind,
    HallucinationReport,
)
from state.ledger.event_store import append_event

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_LOOP_DEPTH = 3
SIGNAL_RETENTION_HOURS = 24

_RETENTION_NS = SIGNAL_RETENTION_HOURS * 3_600_000_000_000


class HallucinationGuard:
    """
    Tracks the provenance DAG of learning signals to detect self-referential
    loops and paper-to-live contamination.
    """

    def __init__(self) -> None:
        # signal_id → {
        #   "source": str,
        #   "parent_signal_id": str | None,
        #   "is_external": bool,
        #   "mode": str,  # "paper" | "live" | ...
        #   "ts_ns": int,
        # }
        self._signal_graph: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_signal(
        self,
        signal_id: str,
        source: str,
        parent_signal_id: str | None,
        is_external: bool,
        mode: str,
        ts_ns: int,
    ) -> HallucinationReport:
        """
        Register a learning signal and check for hallucination patterns.

        Returns a HallucinationReport. Callers should check
        report.self_referential before routing the signal to learning.
        """
        with self._lock:
            # Prune stale signals
            self._prune(ts_ns)

            # Register this signal
            self._signal_graph[signal_id] = {
                "source": source,
                "parent_signal_id": parent_signal_id,
                "is_external": is_external,
                "mode": mode,
                "ts_ns": ts_ns,
            }

            # Compute loop depth and paper loop flag
            loop_depth = self._compute_loop_depth(signal_id)
            paper_loop = self._detect_paper_loop(signal_id, mode)

        # Determine severity and violations
        violations: list[CognitiveViolationKind] = []
        evidence: list[str] = []

        if loop_depth >= MAX_LOOP_DEPTH:
            violations.append(CognitiveViolationKind.HALLUCINATION_LOOP)
            evidence.append(f"loop_depth={loop_depth} >= MAX_LOOP_DEPTH={MAX_LOOP_DEPTH}")

        if paper_loop:
            violations.append(CognitiveViolationKind.SYNTHETIC_FEEDBACK)
            evidence.append(f"paper signal mode={mode!r} contaminating live learning loop")

        self_referential = CognitiveViolationKind.HALLUCINATION_LOOP in violations

        if self_referential:
            severity = CognitiveSeverity.CRITICAL
        elif paper_loop:
            severity = CognitiveSeverity.HIGH
        elif loop_depth == MAX_LOOP_DEPTH - 1:
            severity = CognitiveSeverity.WARNING
        else:
            severity = CognitiveSeverity.INFO

        detail = "; ".join(evidence) if evidence else f"depth={loop_depth}, mode={mode!r}, OK"

        report = HallucinationReport(
            ts_ns=ts_ns,
            source=source,
            loop_depth=loop_depth,
            self_referential=self_referential,
            severity=severity,
            evidence=tuple(evidence),
            detail=detail,
        )

        if violations:
            append_event(
                "GOVERNANCE",
                "COGOV_HALLUCINATION_DETECTED",
                "cognitive_governance.hallucination_guard",
                {
                    "signal_id": signal_id,
                    "source": source,
                    "loop_depth": loop_depth,
                    "self_referential": self_referential,
                    "paper_loop": paper_loop,
                    "mode": mode,
                    "severity": severity.value,
                    "violations": [v.value for v in violations],
                    "evidence": list(evidence),
                    "detail": detail,
                },
            )

        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_loop_depth(self, signal_id: str) -> int:
        """
        Walk the parent chain upward until we find an external grounding
        signal or exhaust the graph.

        Returns 0 if this signal is directly external, or the number of
        hops to reach external grounding.  If we hit MAX_LOOP_DEPTH + 1
        without grounding, cap and return MAX_LOOP_DEPTH.
        """
        visited: set[str] = set()
        current_id: str | None = signal_id
        depth = 0

        while current_id is not None:
            if current_id in visited:
                # Cycle detected — treat as maximum depth
                return MAX_LOOP_DEPTH
            visited.add(current_id)

            node = self._signal_graph.get(current_id)
            if node is None:
                # Reached outside the graph — treat as external grounding
                return depth

            if node["is_external"]:
                return depth

            depth += 1
            if depth >= MAX_LOOP_DEPTH:
                return MAX_LOOP_DEPTH

            current_id = node.get("parent_signal_id")

        return depth

    def _detect_paper_loop(self, signal_id: str, mode: str) -> bool:
        """
        Detect if a paper-mode signal is being injected into a learning
        loop that also contains live signals.

        We check if any sibling (same parent) signal in the graph is in
        live mode while this one is in paper mode.
        """
        if mode != "paper":
            return False

        node = self._signal_graph.get(signal_id)
        if node is None:
            return False

        parent_id = node.get("parent_signal_id")
        if parent_id is None:
            # No parent: check if any live signal exists in the graph at all
            # and this paper signal lacks a live parent chain
            return any(
                s["mode"] == "live"
                for sid, s in self._signal_graph.items()
                if sid != signal_id
            )

        # Check siblings (signals sharing the same parent)
        for sid, s in self._signal_graph.items():
            if sid != signal_id and s.get("parent_signal_id") == parent_id:
                if s.get("mode") == "live":
                    return True

        return False

    def _prune(self, current_ts_ns: int) -> None:
        """Remove signals older than SIGNAL_RETENTION_HOURS."""
        cutoff = current_ts_ns - _RETENTION_NS
        stale = [sid for sid, s in self._signal_graph.items() if s["ts_ns"] < cutoff]
        for sid in stale:
            del self._signal_graph[sid]


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: HallucinationGuard | None = None
_lock = threading.Lock()


def get_hallucination_guard() -> HallucinationGuard:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = HallucinationGuard()
    return _instance


__all__ = ["HallucinationGuard", "get_hallucination_guard"]
