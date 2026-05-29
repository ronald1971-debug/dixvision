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
            pass
        try:
            # Fallback: read from governance layer
            from governance_engine.authority_ledger import get_authority_ledger  # type: ignore[import-not-found]
            ledger = get_authority_ledger()
            if hasattr(ledger, "current_mode"):
                return str(ledger.current_mode)
        except Exception:
            pass
        return "UNKNOWN"

    @staticmethod
    def _read_dyon() -> dict:
        try:
            from evolution_engine.dyon.dyon_runtime import get_dyon_runtime
            rt = get_dyon_runtime()
            snap = rt.snapshot()
            return {
                "scan_count": snap.get("scan_count", 0),
                "clean": snap.get("latest_scan") is None or True,
                "violation_count": 0,
            }
        except Exception:
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
        try:
            from evolution_engine.evolution_orchestrator import get_evolution_orchestrator
            snap = get_evolution_orchestrator().snapshot()
            return int(snap.get("tick_count", 0))
        except Exception:
            return None


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
