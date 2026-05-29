"""state.state_sync — Unified System State Snapshot.

Single aggregation point for the state of every cognitive subsystem.
Gives the operator and the UnifiedCognitiveKernel one consistent view
of the entire system at any moment.

Covered subsystems:
  market      — MarketState (price LKV, trend, regime, volatility)
  risk        — RiskTracker (drawdown, halted, positions)
  indira      — IndiraRuntime (thought count, confidence, top archetype)
  dyon        — DyonRuntime (violation count, proposal count)
  evolution   — EvolutionOrchestrator (tick count, loop states)
  simulation  — SimulationDominanceRuntime (dominance scoreboard)
  memory      — MemoryOrchestrator (episodic/semantic/procedural sizes)
  governance  — CognitiveGovernanceEngine (guard status)
  spine       — CognitiveSpine (tick_seq, phase_errors, active phases)

All reads are best-effort — a failing subsystem returns {"error": "..."}
rather than raising.

Authority: state tier — no execution_engine imports.
INV-15: ts_ns is caller-supplied; used in the snapshot header only.
"""

from __future__ import annotations

import threading
from typing import Any

_EMPTY: dict[str, Any] = {}


class UnifiedStateSync:
    """Aggregates live snapshots from every subsystem into one call."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_snapshot: dict[str, Any] = {}
        self._snapshot_seq: int = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def snapshot(self, *, ts_ns: int) -> dict[str, Any]:
        """Return a complete system state snapshot.

        Pulls from all singletons; failures return {"error": "..."} per key.
        The result is cached as self._last_snapshot for cheap reads.
        """
        out: dict[str, Any] = {
            "ts_ns": ts_ns,
            "seq": 0,
        }

        out["market"] = self._read_market()
        out["risk"] = self._read_risk()
        out["indira"] = self._read_indira()
        out["dyon"] = self._read_dyon()
        out["evolution"] = self._read_evolution()
        out["simulation"] = self._read_simulation()
        out["memory"] = self._read_memory()
        out["governance"] = self._read_governance()
        out["spine"] = self._read_spine()

        with self._lock:
            self._snapshot_seq += 1
            out["seq"] = self._snapshot_seq
            self._last_snapshot = out

        return out

    def last(self) -> dict[str, Any]:
        """Return the most recent snapshot without re-reading."""
        with self._lock:
            return dict(self._last_snapshot)

    # ------------------------------------------------------------------
    # Per-subsystem readers (best-effort, never raise)
    # ------------------------------------------------------------------

    @staticmethod
    def _read_market() -> dict[str, Any]:
        try:
            from state.market_state import get_market_state
            ms = get_market_state()
            return {
                "regime": ms.regime(),
                "trend": ms.trend(),
                "context": ms.format_for_context(),
            }
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _read_risk() -> dict[str, Any]:
        try:
            from governance_engine.risk_engine.risk_tracker import get_risk_tracker
            snap = get_risk_tracker().snapshot()
            return {
                "halted": snap.get("halted", False),
                "breach_reason": snap.get("breach_reason", ""),
                "drawdown_pct": snap.get("drawdown_pct", 0.0),
                "realized_pnl": snap.get("realized_pnl", 0.0),
                "positions": len(snap.get("open_positions", {})),
            }
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _read_indira() -> dict[str, Any]:
        try:
            from intelligence_engine.cognitive.indira_runtime import get_indira_runtime
            snap = get_indira_runtime().snapshot()
            return {
                "tick_count": snap.get("tick_count", 0),
                "thought_count": snap.get("thought_count", 0),
                "confidence": snap.get("confidence_baseline", 0.0),
                "top_archetype": snap.get("trader_intelligence", {}).get("top_archetype", ""),
            }
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _read_dyon() -> dict[str, Any]:
        try:
            from evolution_engine.dyon.dyon_runtime import get_dyon_runtime
            snap = get_dyon_runtime().snapshot()
            return {
                "tick_count": snap.get("tick_count", 0),
                "violation_count": snap.get("violation_count", 0),
                "proposal_count": snap.get("proposal_count", 0),
                "clean": snap.get("clean", True),
            }
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _read_evolution() -> dict[str, Any]:
        try:
            from evolution_engine.evolution_orchestrator import get_evolution_orchestrator
            snap = get_evolution_orchestrator().snapshot()
            return {
                "tick_count": snap.get("tick_count", 0),
                "loops_wired": snap.get("loops_wired", 0),
            }
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _read_simulation() -> dict[str, Any]:
        try:
            from simulation.dominance_runtime import get_simulation_dominance_runtime
            snap = get_simulation_dominance_runtime().snapshot()
            return {
                "active": snap.get("active", False),
                "dominance_achieved": snap.get("dominance_achieved", False),
                "champion": snap.get("champion", ""),
                "total_tournaments": snap.get("total_tournaments", 0),
            }
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _read_memory() -> dict[str, Any]:
        try:
            from state.memory_tensor.memory_orchestrator import get_memory_orchestrator
            snap = get_memory_orchestrator().snapshot()
            return {
                "episodic": snap.get("episodic_size", 0),
                "semantic": snap.get("semantic_size", 0),
                "procedural": snap.get("procedural_size", 0),
                "consolidate_seq": snap.get("consolidate_seq", 0),
            }
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _read_governance() -> dict[str, Any]:
        try:
            from cognitive_governance.engine import get_cognitive_governance
            snap = get_cognitive_governance().snapshot()
            return {
                "active_guards": snap.get("active_guards", 0),
                "violations_today": snap.get("violations_today", 0),
                "last_emission": snap.get("last_emission_iso", ""),
            }
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _read_spine() -> dict[str, Any]:
        try:
            from runtime.cognitive_spine import get_cognitive_spine
            snap = get_cognitive_spine().snapshot()
            return {
                "active": snap.get("active", False),
                "tick_seq": snap.get("tick_seq", 0),
                "phase_errors": snap.get("phase_errors", {}),
            }
        except Exception as exc:
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_sync: UnifiedStateSync | None = None
_sync_lock = threading.Lock()


def get_state_sync() -> UnifiedStateSync:
    global _sync
    with _sync_lock:
        if _sync is None:
            _sync = UnifiedStateSync()
    return _sync


__all__ = [
    "UnifiedStateSync",
    "get_state_sync",
]
