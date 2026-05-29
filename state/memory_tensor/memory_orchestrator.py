"""MemoryOrchestrator — unified memory orchestration layer (CONSOLIDATION PHASE).

Single entry point for all memory writes and queries across every memory kind:

    EPISODIC     — trade episodes (context, action, outcome, reward)
    SEMANTIC     — vector-indexed knowledge (beliefs, patterns, research)
    PROCEDURAL   — action-outcome sequences (how to act in a situation)
    META         — strategy insights and regime patterns
    REGRET       — counterfactual regret log (missed, early-exit, oversized)

All concrete stores are lazily imported and remain implementation details.
Callers only need this module; they never import individual store classes.

Authority: pure state tier — no engine, no runtime, no execution imports.
INV-15: consolidate(ts_ns) is caller-driven; no internal clock reads.
"""

from __future__ import annotations

from typing import Any

from state.memory_tensor.contracts import Episode, MemoryQuery, MemoryResult


class MemoryOrchestrator:
    """Coordinates all memory stores behind a single interface.

    Stores are lazily instantiated on first access to keep import cost
    at module-load time to zero.
    """

    def __init__(self) -> None:
        self._episodic: Any = None
        self._semantic: Any = None
        self._procedural: Any = None
        self._meta: Any = None
        self._regret: Any = None
        self._consolidate_seq: int = 0

    # ------------------------------------------------------------------
    # Store accessors (lazy)
    # ------------------------------------------------------------------

    @property
    def episodic(self) -> Any:
        if self._episodic is None:
            from state.memory_tensor.episodic import EpisodicMemoryStore
            self._episodic = EpisodicMemoryStore()
        return self._episodic

    @property
    def semantic(self) -> Any:
        if self._semantic is None:
            from state.memory_tensor.semantic import SemanticMemoryStore
            self._semantic = SemanticMemoryStore(dim=64, max_size=10_000)
        return self._semantic

    @property
    def procedural(self) -> Any:
        if self._procedural is None:
            from state.memory_tensor.procedural import ProceduralMemoryStore
            self._procedural = ProceduralMemoryStore()
        return self._procedural

    @property
    def meta(self) -> Any:
        if self._meta is None:
            from state.memory_tensor.meta_memory import MetaMemoryStore
            self._meta = MetaMemoryStore()
        return self._meta

    @property
    def regret(self) -> Any:
        if self._regret is None:
            from state.memory_tensor.regret.regret_log import RegretLog
            self._regret = RegretLog()
        return self._regret

    # ------------------------------------------------------------------
    # Unified write interface
    # ------------------------------------------------------------------

    def write_episode(self, episode: Episode) -> None:
        try:
            self.episodic.add(episode)
        except Exception:
            pass

    def write_semantic(self, episode: Episode) -> None:
        try:
            self.semantic.add(episode)
        except Exception:
            pass

    def write_procedural(self, episode: Episode) -> None:
        try:
            self.procedural.add(episode)
        except Exception:
            pass

    def write_meta(self, insight: Any) -> None:
        try:
            store = self.meta
            if hasattr(store, "add"):
                store.add(insight)
            elif hasattr(store, "record"):
                store.record(insight)
        except Exception:
            pass

    def add_regret(self, entry: Any) -> None:
        try:
            store = self.regret
            if hasattr(store, "add"):
                store.add(entry)
            elif hasattr(store, "record"):
                store.record(entry)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Unified query interface
    # ------------------------------------------------------------------

    def query_episodic(self, query: MemoryQuery) -> MemoryResult | None:
        try:
            return self.episodic.search(query)
        except Exception:
            return None

    def query_semantic(self, query: MemoryQuery) -> MemoryResult | None:
        try:
            return self.semantic.search(query)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Consolidation tick — called by IndiraRuntime on each cognitive tick
    # ------------------------------------------------------------------

    def consolidate(self, *, ts_ns: int) -> None:
        """Periodic memory consolidation pass (best-effort, never raises)."""
        self._consolidate_seq += 1
        # Emit memory formation event every 10 consolidations so the
        # INDIRA cognitive stream shows memory activity.
        if self._consolidate_seq % 10 == 0:
            try:
                from intelligence_engine.cognitive.observability_emitter import (
                    emit_memory_formation,
                )
                emit_memory_formation(
                    ts_ns=ts_ns,
                    memory_kind="EPISODIC",
                    content_summary=(
                        f"consolidation pass {self._consolidate_seq}: "
                        f"episodic={len(self._episodic) if self._episodic else 0} "
                        f"semantic={len(self._semantic) if self._semantic else 0}"
                    ),
                    source="memory_orchestrator",
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Snapshot for dashboard / observability
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        return {
            "episodic_size": len(self._episodic) if self._episodic else 0,
            "semantic_size": len(self._semantic) if self._semantic else 0,
            "procedural_size": len(self._procedural) if self._procedural else 0,
            "consolidate_seq": self._consolidate_seq,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_orchestrator: MemoryOrchestrator | None = None


def get_memory_orchestrator() -> MemoryOrchestrator:
    """Return the module-level singleton MemoryOrchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MemoryOrchestrator()
    return _orchestrator


__all__ = [
    "MemoryOrchestrator",
    "get_memory_orchestrator",
]
