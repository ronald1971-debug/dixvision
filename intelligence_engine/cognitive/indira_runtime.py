"""INDIRA Runtime — unified cognitive entry point (CONSOLIDATION PHASE).

Single façade over all INDIRA cognitive subsystems:
    ThoughtRuntime      — always-on reasoning loop (primary driver)
    ReflectionEngine    — meta-thought synthesis from historical thoughts
    EnvironmentAwareness — live system state context injection
    DebateGraph         — LLM-backed multi-agent deliberation (optional)
    MemoryOrchestrator  — episodic / semantic / regret memory (optional)

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
        self._tick_seq: int = 0
        # Seed the ring buffer with thoughts from the previous process run.
        # Best-effort: if the event store isn't ready yet (early import),
        # we start with an empty history and restore on the first tick.
        self._restore_from_ledger()
        # Activate DYON→INDIRA event bus coupling.  Best-effort — if the bus
        # is not yet available the bridge retries silently on next access.
        self._activate_dyon_bridge()

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
        self._tick_seq += 1

        # On autonomous ticks (no market override), build context from
        # live system state so ThoughtRuntime reasons about real conditions.
        if context_override is None:
            context_override = self._try_environment_context(ts_ns)

        thought = self._thought.tick(
            ts_ns=ts_ns,
            context_override=context_override,
            conclusion_override=conclusion_override,
            confidence_override=confidence_override,
        )
        self._try_debate_hook(ts_ns)
        self._try_memory_hook(ts_ns)
        self._try_backtesting_hook(ts_ns)
        # Slow-loop parameter evolution every 20 ticks — persists learned
        # confidence_baseline and other free parameters across restarts.
        if self._tick_seq % 20 == 0:
            self._try_learning_hook(ts_ns)
        # Reflective synthesis every 10 ticks — INDIRA looks back at her
        # own reasoning stream and emits a meta-thought.
        if self._tick_seq % 10 == 0:
            self._try_reflection_hook(ts_ns)
        # Long-horizon pattern extraction every 50 ticks — produces Insights
        # that persist across restarts and shape future thought context.
        if self._tick_seq % 50 == 0:
            self._try_long_horizon_hook(ts_ns)
        # Trader archetype arena evaluation every 100 ticks — updates the
        # dominant trading archetype injected into INDIRA's context.
        if self._tick_seq % 100 == 0:
            self._try_trader_intelligence_hook(ts_ns)
        return thought

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def snapshot(self, limit: int = 20) -> dict[str, Any]:
        """JSON-serialisable snapshot of INDIRA's current cognitive state."""
        snap = self._thought.snapshot(limit)
        snap["runtime"] = "IndiraRuntime"
        try:
            from intelligence_engine.cognitive.long_horizon_memory import (
                get_long_horizon_memory,
            )
            lhm = get_long_horizon_memory()
            snap["long_horizon"] = lhm.snapshot()
        except Exception:
            pass
        try:
            from intelligence_engine.learning.learning_persistence import (
                get_learning_persistence,
            )
            snap["learning"] = get_learning_persistence().snapshot()
        except Exception:
            pass
        try:
            from intelligence_engine.cognitive.trader_intelligence_runtime import (
                get_trader_intelligence_runtime,
            )
            snap["trader_intelligence"] = get_trader_intelligence_runtime().snapshot()
        except Exception:
            pass
        return snap

    def recent(self, limit: int = 20) -> list[Thought]:
        return self._thought.recent(limit)

    @property
    def thought_runtime(self) -> ThoughtRuntime:
        return self._thought

    # ------------------------------------------------------------------
    # Boot-time cognitive continuity
    # ------------------------------------------------------------------

    def _restore_from_ledger(self, limit: int = 200) -> int:
        """Read the most recent thoughts from the ledger and seed the buffer.

        Called once at construction so INDIRA remembers her last conclusions
        across process restarts.  Returns the number of thoughts loaded.
        Never raises.
        """
        try:
            import json as _json
            from state.ledger.event_store import get_event_store
            store = get_event_store()
            # Overfetch by 3× because INDIRA emits non-thought events too;
            # they share the same event_type/source bucket.
            rows = store.query(
                event_type="INTELLIGENCE",
                source="INDIRA",
                limit=limit * 3,
            )
            thoughts: list[Thought] = []
            for row in rows:
                if row.get("sub_type") != "THOUGHT_STREAM":
                    continue
                raw = row.get("payload", "{}")
                p = _json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(p, dict):
                    continue
                thought_id = str(p.get("thought_id", ""))
                if not thought_id:
                    continue
                # ts_ns is encoded in the thought_id:
                # "indira_thought_{tick_count}_{ts_ns}"
                try:
                    ts_ns = int(thought_id.rsplit("_", 1)[-1])
                except (ValueError, IndexError):
                    ts_ns = 0
                try:
                    thoughts.append(Thought(
                        thought_id=thought_id,
                        ts_ns=ts_ns,
                        step=str(p.get("reasoning_step", "self_reflection")),
                        context=str(p.get("context", "")),
                        conclusion=str(p.get("conclusion", "")),
                        confidence=float(p.get("confidence", 0.65)),
                    ))
                except (ValueError, TypeError):
                    continue
                if len(thoughts) >= limit:
                    break
            loaded = self._thought.restore(thoughts)
            if loaded:
                import logging
                logging.getLogger(__name__).info(
                    "IndiraRuntime: restored %d thoughts from ledger", loaded
                )
            return loaded
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Optional extension hooks (best-effort, never raise)
    # ------------------------------------------------------------------

    def _try_environment_context(self, ts_ns: int) -> str | None:
        """Return a live context string from EnvironmentAwareness + long-horizon insights."""
        parts: list[str] = []
        try:
            from intelligence_engine.cognitive.environment_awareness import (
                get_environment_awareness,
            )
            env = get_environment_awareness().build_context(ts_ns=ts_ns)
            if env:
                parts.append(env)
        except Exception:
            pass
        try:
            from intelligence_engine.cognitive.long_horizon_memory import (
                get_long_horizon_memory,
            )
            lhm_ctx = get_long_horizon_memory().format_for_context(ts_ns=ts_ns, limit=2)
            if lhm_ctx:
                parts.append(lhm_ctx)
        except Exception:
            pass
        try:
            from intelligence_engine.cognitive.trader_intelligence_runtime import (
                get_trader_intelligence_runtime,
            )
            ti_ctx = get_trader_intelligence_runtime().format_for_context()
            if ti_ctx:
                parts.append(ti_ctx)
        except Exception:
            pass
        return " ".join(parts) if parts else None

    def _try_reflection_hook(self, ts_ns: int) -> None:
        """Synthesise a meta-thought from recent thought history."""
        try:
            from intelligence_engine.cognitive.reflection_engine import (
                get_reflection_engine,
            )
            thoughts = list(self._thought.recent(20))
            get_reflection_engine().reflect(thoughts, ts_ns=ts_ns)
        except Exception:
            pass

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

    def _try_learning_hook(self, ts_ns: int) -> None:
        """Drive the slow-loop learner and propagate learned confidence_baseline.

        Also flushes DYON→INDIRA feedback from the event bus bridge so
        architectural health signals reach the learner before each tick.
        """
        # Flush DYON signals first so they are included in this tick.
        try:
            from intelligence_engine.cognitive.dyon_signal_bridge import (
                get_dyon_signal_bridge,
            )
            get_dyon_signal_bridge().flush(ts_ns=ts_ns)
        except Exception:
            pass
        try:
            from intelligence_engine.learning.learning_persistence import (
                get_learning_persistence,
            )
            lp = get_learning_persistence()
            snap = lp.tick(ts_ns=ts_ns)
            # Propagate the learned confidence_baseline into ThoughtRuntime.
            new_baseline = snap.values.get("confidence_baseline")
            if new_baseline is not None and not snap.frozen:
                self._thought.set_confidence_baseline(new_baseline)
        except Exception:
            pass

    @staticmethod
    def _activate_dyon_bridge() -> None:
        """Activate the DYON→INDIRA event bus bridge (best-effort)."""
        try:
            from intelligence_engine.cognitive.dyon_signal_bridge import (
                get_dyon_signal_bridge,
            )
            get_dyon_signal_bridge()   # activates on first access
        except Exception:
            pass

    def _try_long_horizon_hook(self, ts_ns: int) -> None:
        """Consolidate long-horizon memory — extract insights across the full ledger."""
        try:
            from intelligence_engine.cognitive.long_horizon_memory import (
                get_long_horizon_memory,
            )
            get_long_horizon_memory().consolidate(ts_ns=ts_ns)
        except Exception:
            pass

    def _try_trader_intelligence_hook(self, ts_ns: int) -> None:
        """Run a trader archetype arena round and update the dominant archetype."""
        try:
            from intelligence_engine.cognitive.trader_intelligence_runtime import (
                get_trader_intelligence_runtime,
            )
            get_trader_intelligence_runtime().tick(ts_ns=ts_ns)
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
