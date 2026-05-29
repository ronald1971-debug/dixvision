"""DYON Runtime — autonomous engineering intelligence loop (COGNITIVE ACTIVATION PHASE).

DYON continuously monitors the system's own architecture. This module owns the
always-on DYON runtime: periodic topology scans, patch proposal tracking, and a
structured snapshot of DYON's current engineering assessment.

Design:
* ``tick(ts_ns)`` runs a topology scan every ``scan_interval`` ticks.
* Scan results are cached so ``latest_scan()`` never blocks.
* All ledger writes go through dyon_observability_emitter (best-effort).
* ``snapshot()`` returns a frozen dict safe for JSON serialisation.

INV-15: timestamps are caller-supplied. No wall-clock reads inside tick().

Authority (L2/B1): imports only from evolution_engine.* and core.*.
Never imports intelligence_engine or execution_engine.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any

from evolution_engine.dyon.topology_scanner import (
    DyonTopologyScanner,
    TopologyScanResult,
    TopologyViolation,
    get_scanner,
)


# ---------------------------------------------------------------------------
# Patch proposal record (lightweight, not the full PatchProposal contract)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DyonPatchProposal:
    """DYON's self-generated engineering proposal from a scan finding."""

    proposal_id: str
    ts_ns: int
    invariant_id: str      # "B1" | "L2" | "L3" | "INV-15"
    source_module: str
    imported_module: str
    severity: str          # "CRITICAL" | "WARNING"
    description: str
    recommended_action: str


# ---------------------------------------------------------------------------
# DyonRuntime
# ---------------------------------------------------------------------------


class DyonRuntime:
    """DYON's always-on engineering intelligence runtime.

    Args:
        repo_root: Path to the repository root for topology scans.
        scan_interval: Tick cadence between scans. 1 = scan every tick.
        max_proposal_history: Rolling buffer for recent proposals.
    """

    def __init__(
        self,
        *,
        repo_root: str | pathlib.Path = ".",
        scan_interval: int = 50,
        max_proposal_history: int = 500,
    ) -> None:
        self._root = pathlib.Path(repo_root)
        self._scan_interval = max(1, scan_interval)
        self._scanner: DyonTopologyScanner = get_scanner()
        self._tick_count: int = 0
        self._scan_count: int = 0
        self._last_scan: TopologyScanResult | None = None
        self._proposals: list[DyonPatchProposal] = []
        self._max_proposals = max_proposal_history

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def tick(self, *, ts_ns: int) -> TopologyScanResult | None:
        """Advance one DYON runtime tick; scan when the interval fires.

        Returns the scan result if a scan ran this tick, else ``None``.
        """
        self._tick_count += 1
        if self._tick_count % self._scan_interval != 0:
            return None

        self._scan_count += 1
        try:
            result = self._scanner.scan_and_emit(self._root, ts_ns=ts_ns)
        except Exception:  # pragma: no cover
            return None

        self._last_scan = result
        self._generate_proposals(result, ts_ns)
        return result

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    @property
    def latest_scan(self) -> TopologyScanResult | None:
        return self._last_scan

    @property
    def scan_count(self) -> int:
        return self._scan_count

    @property
    def tick_count(self) -> int:
        return self._tick_count

    def recent_proposals(self, limit: int = 50) -> list[DyonPatchProposal]:
        """Return the most recent proposals, newest-first."""
        return list(reversed(self._proposals))[:limit]

    def snapshot(self, proposal_limit: int = 20) -> dict[str, Any]:
        """Return a JSON-serialisable snapshot of DYON's current state."""
        scan = self._last_scan
        return {
            "intelligence": "DYON",
            "tick_count": self._tick_count,
            "scan_count": self._scan_count,
            "scan_interval": self._scan_interval,
            "latest_scan": _scan_to_dict(scan) if scan else None,
            "recent_proposals": [
                _proposal_to_dict(p) for p in self.recent_proposals(proposal_limit)
            ],
        }

    def topology_report(self) -> dict[str, Any]:
        """Full topology report from the latest scan."""
        scan = self._last_scan
        if scan is None:
            return {
                "status": "no_scan_yet",
                "files_scanned": 0,
                "violations": [],
                "clean": True,
            }
        return _scan_to_dict(scan)

    # ------------------------------------------------------------------
    # Proposal generation
    # ------------------------------------------------------------------

    def _generate_proposals(self, result: TopologyScanResult, ts_ns: int) -> None:
        """Convert scan violations into DyonPatchProposals and emit them."""
        for i, v in enumerate(result.violations):
            proposal = DyonPatchProposal(
                proposal_id=f"dyon_patch_{ts_ns}_{i}",
                ts_ns=ts_ns,
                invariant_id=v.invariant_id,
                source_module=v.source_module,
                imported_module=v.imported_module,
                severity=v.severity,
                description=v.description,
                recommended_action=(
                    f"Remove direct import of '{v.imported_module}' "
                    f"from '{v.source_module}'; route through core.contracts."
                ),
            )
            self._proposals.append(proposal)
            if len(self._proposals) > self._max_proposals:
                self._proposals = self._proposals[-self._max_proposals:]
            self._emit_proposal(proposal)

    @staticmethod
    def _emit_proposal(proposal: "DyonPatchProposal") -> None:
        """Best-effort PatchProposalEvent emission. Never raises."""
        try:
            from evolution_engine.charter.dyon_observability_emitter import (
                emit_patch_proposal,
            )
            emit_patch_proposal(
                ts_ns=proposal.ts_ns,
                proposal_id=proposal.proposal_id,
                target_module=proposal.source_module,
                patch_kind="ARCHITECTURAL_FIX",
                description=proposal.description,
                rationale=f"invariant_id={proposal.invariant_id}",
                governance_status="PROPOSED",
            )
        except Exception:  # pragma: no cover
            pass


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _violation_to_dict(v: TopologyViolation) -> dict[str, Any]:
    return {
        "invariant_id": v.invariant_id,
        "rule": v.rule,
        "source_module": v.source_module,
        "imported_module": v.imported_module,
        "line": v.line,
        "severity": v.severity,
        "description": v.description,
    }


def _scan_to_dict(scan: TopologyScanResult) -> dict[str, Any]:
    return {
        "ts_ns": scan.ts_ns,
        "root": scan.root,
        "files_scanned": scan.files_scanned,
        "scan_duration_ms": round(scan.scan_duration_ms, 2),
        "violation_count": scan.violation_count,
        "critical_count": len(scan.critical_violations),
        "warning_count": len(scan.warning_violations),
        "clean": scan.is_clean(),
        "violations": [_violation_to_dict(v) for v in scan.violations],
    }


def _proposal_to_dict(p: DyonPatchProposal) -> dict[str, Any]:
    return {
        "proposal_id": p.proposal_id,
        "ts_ns": p.ts_ns,
        "invariant_id": p.invariant_id,
        "source_module": p.source_module,
        "imported_module": p.imported_module,
        "severity": p.severity,
        "description": p.description,
        "recommended_action": p.recommended_action,
    }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_runtime: DyonRuntime | None = None


def get_dyon_runtime(*, repo_root: str | pathlib.Path = ".") -> DyonRuntime:
    """Return the module-level singleton DyonRuntime."""
    global _runtime
    if _runtime is None:
        _runtime = DyonRuntime(repo_root=repo_root, scan_interval=50)
    return _runtime


__all__ = [
    "DyonPatchProposal",
    "DyonRuntime",
    "get_dyon_runtime",
]
