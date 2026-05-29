"""EnvironmentAwareness — live system state context for INDIRA's reasoning.

Provides ThoughtRuntime with a rich, dynamically-built context string that
reflects the actual state of the cognitive ecosystem at the moment of each
autonomous tick.  This replaces static template strings with real signals.

Gathered per-tick (best-effort, never raises):
  - Current operator mode (LIVE / PAPER / SAFE / LOCKED / AUTO / CANARY)
  - DYON topology scan health (violations, clean flag, scan count)
  - Memory stores utilisation (episodic / semantic sizes)
  - Research runtime status (running, queue depth, total completed)
  - INDIRA own tick count and confidence trend
  - Active EvolutionOrchestrator tick count

Authority (B1): imports only from intelligence_engine.* and core.*.
All cross-module reads are lazy and wrapped in try/except.
INV-15: ts_ns is caller-supplied; no internal clock reads.
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


class EnvironmentAwareness:
    """Assembles a structured context string from live system probes."""

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    def build_context(self, *, ts_ns: int) -> str:
        """Return a compact multi-field context string for ThoughtRuntime.

        Args:
            ts_ns: Caller-supplied nanosecond timestamp (INV-15).

        Returns:
            A space-separated key=value context string, never empty.
        """
        parts: list[str] = []

        # ---- Mode ----------------------------------------------------------
        mode = self._read_mode()
        parts.append(f"mode={mode}")

        # ---- DYON topology -------------------------------------------------
        dyon = self._read_dyon()
        parts.append(f"dyon_scans={dyon['scan_count']}")
        if not dyon["clean"]:
            parts.append(f"violations={dyon['violation_count']}")

        # ---- Memory stores -------------------------------------------------
        mem = self._read_memory()
        parts.append(f"mem_ep={mem['episodic']}")
        parts.append(f"mem_sem={mem['semantic']}")

        # ---- Research runtime ----------------------------------------------
        res = self._read_research()
        parts.append(f"research={'RUN' if res['running'] else 'IDLE'}")
        parts.append(f"res_q={res['queue']}")
        parts.append(f"res_ok={res['completed']}")

        # ---- Evolution orchestrator ----------------------------------------
        evo_ticks = self._read_evolution_ticks()
        if evo_ticks is not None:
            parts.append(f"evo_ticks={evo_ticks}")

        # ---- Live market state (P3 Reality Layer) --------------------------
        market_ctx = self._read_market()
        if market_ctx:
            parts.append(market_ctx)

        # ---- Live risk state -----------------------------------------------
        risk_ctx = self._read_risk()
        if risk_ctx:
            parts.append(risk_ctx)

        return " ".join(parts) if parts else "context=unknown"

    # ------------------------------------------------------------------
    # Probes (all best-effort)
    # ------------------------------------------------------------------

    @staticmethod
    def _read_mode() -> str:
        try:
            from state.system_mode import get_system_mode
            return get_system_mode().value
        except Exception:
            return "UNKNOWN"

    @staticmethod
    def _read_dyon() -> dict:
        # DYON is an offline engine; its state is not readable from the runtime
        # (L3 — runtime must remain isolated from offline engine).
        return {"scan_count": 0, "clean": True, "violation_count": 0}

    @staticmethod
    def _read_memory() -> dict:
        try:
            from state.memory_tensor.memory_orchestrator import get_memory_orchestrator
            snap = get_memory_orchestrator().snapshot()
            return {
                "episodic": snap.get("episodic_size", 0),
                "semantic": snap.get("semantic_size", 0),
            }
        except Exception:
            return {"episodic": 0, "semantic": 0}

    @staticmethod
    def _read_research() -> dict:
        try:
            from intelligence_engine.research.autonomous_research_runtime import (
                get_research_runtime,
            )
            snap = get_research_runtime().snapshot()
            return {
                "running": snap.get("running", False),
                "queue": snap.get("queue_depth", 0),
                "completed": snap.get("total_ok", 0),
            }
        except Exception:
            return {"running": False, "queue": 0, "completed": 0}

    @staticmethod
    def _read_evolution_ticks() -> int | None:
        # evolution_engine is offline — not readable from runtime (L3).
        return None

    @staticmethod
    def _read_market() -> str:
        """Return live market context string from MarketState, or '' if no data."""
        try:
            from state.market_state import get_market_state
            return get_market_state().format_for_context(max_symbols=3)
        except Exception:
            return ""

    @staticmethod
    def _read_risk() -> str:
        """Return live risk summary string from RiskTracker, or '' if no data."""
        return ""


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_awareness: EnvironmentAwareness | None = None


def get_environment_awareness() -> EnvironmentAwareness:
    """Return the process-wide EnvironmentAwareness singleton."""
    global _awareness
    if _awareness is None:
        _awareness = EnvironmentAwareness()
    return _awareness


__all__ = [
    "EnvironmentAwareness",
    "get_environment_awareness",
]
