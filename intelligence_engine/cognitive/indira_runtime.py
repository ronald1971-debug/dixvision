"""INDIRA Runtime — unified cognitive entry point (CONSOLIDATION PHASE).

Single façade over all INDIRA cognitive subsystems:
    ThoughtRuntime   — always-on reasoning loop (primary driver)
    DebateGraph      — LLM-backed multi-agent deliberation (optional)
    MemoryOrchestrator — episodic / semantic / regret memory (optional)

Boot wires to this class only. Underlying fragments remain as
implementation details; nothing outside this module needs to know about
ThoughtRuntime directly.

Authority (B1): imports only from intelligence_engine.* and core.*.
INV-15: tick() is side-effect-free wrt wall clock; ts_ns is caller-supplied.
"""

from __future__ import annotations

from typing import Any

from intelligence_engine.cognitive.thought_runtime import (
    Thought,
    ThoughtRuntime,
    get_thought_runtime,
)


class IndiraRuntime:
    """Unified INDIRA cognitive runtime.

    Args:
        thought_runtime: The ThoughtRuntime instance to drive.  If None,
            ``get_thought_runtime()`` is used so the singleton is shared.
    """

    def __init__(self, *, thought_runtime: ThoughtRuntime | None = None) -> None:
        self._thought = thought_runtime or get_thought_runtime()

    # ------------------------------------------------------------------
    # Primary tick — drives the full cognitive pipeline
    # ------------------------------------------------------------------

    def tick(
        self,
        *,
        ts_ns: int,
        context_override: str | None = None,
        conclusion_override: str | None = None,
        confidence_override: float | None = None,
    ) -> Thought:
        """Advance INDIRA's cognitive cycle by one step.

        Drives ThoughtRuntime, then optionally invokes debate graph and
        memory consolidation hooks if they are available and not frozen.

        Returns:
            The :class:`Thought` produced by the reasoning loop.
        """
        thought = self._thought.tick(
            ts_ns=ts_ns,
            context_override=context_override,
            conclusion_override=conclusion_override,
            confidence_override=confidence_override,
        )
        self._try_debate_hook(ts_ns)
        self._try_memory_hook(ts_ns)
        self._try_backtesting_hook(ts_ns)
        return thought

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def snapshot(self, limit: int = 20) -> dict[str, Any]:
        """JSON-serialisable snapshot of INDIRA's current cognitive state."""
        snap = self._thought.snapshot(limit)
        snap["runtime"] = "IndiraRuntime"
        return snap

    def recent(self, limit: int = 20) -> list[Thought]:
        return self._thought.recent(limit)

    @property
    def thought_runtime(self) -> ThoughtRuntime:
        return self._thought

    # ------------------------------------------------------------------
    # Optional extension hooks (best-effort, never raise)
    # ------------------------------------------------------------------

    def _try_debate_hook(self, ts_ns: int) -> None:
        try:
            from intelligence_engine.cognitive.debate_graph import get_debate_graph  # type: ignore[attr-defined]
            graph = get_debate_graph()
            if hasattr(graph, "tick"):
                graph.tick(ts_ns=ts_ns)
        except Exception:
            pass

    def _try_memory_hook(self, ts_ns: int) -> None:
        try:
            from state.memory_tensor.memory_orchestrator import get_memory_orchestrator
            get_memory_orchestrator().consolidate(ts_ns=ts_ns)
        except Exception:
            pass

    def _try_backtesting_hook(self, ts_ns: int) -> None:
        """Probe known platforms and enqueue discovery research (every 10th tick)."""
        if not hasattr(self, "_bt_tick"):
            self._bt_tick = 0  # type: ignore[attr-defined]
        self._bt_tick += 1  # type: ignore[attr-defined]
        if self._bt_tick % 10 != 0:  # type: ignore[attr-defined]
            return
        try:
            from intelligence_engine.backtesting import get_platform_registry
            registry = get_platform_registry()
            registry.probe_cycle(ts_ns=ts_ns)
            registry.research_cycle(ts_ns=ts_ns)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_runtime: IndiraRuntime | None = None


def get_indira_runtime() -> IndiraRuntime:
    """Return the module-level singleton IndiraRuntime.

    The underlying ThoughtRuntime is the same singleton returned by
    ``get_thought_runtime()``, so IntelligenceEngine._emit_cognition_events
    and IndiraRuntime.tick() share one thought buffer.
    """
    global _runtime
    if _runtime is None:
        _runtime = IndiraRuntime(thought_runtime=get_thought_runtime())
    return _runtime


__all__ = [
    "IndiraRuntime",
    "get_indira_runtime",
]
