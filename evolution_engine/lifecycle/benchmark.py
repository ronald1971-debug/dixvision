"""evolution_engine.lifecycle.benchmark — Stage 4: baseline benchmark comparison.

BenchmarkEngine compares the proposal's simulation fitness against the
current dominant strategy from SimulationDominanceRuntime.  A proposal
passes if its delta_vs_baseline is ≥ BENCHMARK_MIN_DELTA.

When the dominance runtime is unavailable, falls back to a synthetic delta
derived deterministically from the simulation fitness.

Authority (L2/B1): stdlib only at module level.
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evolution_engine.lifecycle.contracts import BenchmarkResult, ProposalRecord

_logger = logging.getLogger(__name__)

BENCHMARK_MIN_DELTA: float = -5.0    # minimum delta to pass (allows slight regression)


class BenchmarkEngine:
    """Compares a proposal's fitness against the simulation champion.

    Lazy-imports SimulationDominanceRuntime to get the champion fitness.
    Falls back to synthetic champion when unavailable.
    """

    def __init__(self, *, min_delta: float = BENCHMARK_MIN_DELTA) -> None:
        self._min_delta = min_delta
        self._lock = threading.Lock()
        self._bench_count: int = 0

    def run(self, record: "ProposalRecord", ts_ns: int) -> "BenchmarkResult":
        """Benchmark *record* against the current simulation champion.

        Returns a :class:`BenchmarkResult`; never raises.
        """
        from evolution_engine.lifecycle.contracts import BenchmarkResult

        with self._lock:
            self._bench_count += 1

        sim = record.simulation_result
        proposal_fitness = sim.fitness if sim is not None else 0.0
        champion_fitness, notes_prefix = self._get_champion_fitness()
        delta = proposal_fitness - champion_fitness
        passed = delta >= self._min_delta
        notes = (
            f"{notes_prefix} proposal={proposal_fitness:.2f} "
            f"champion={champion_fitness:.2f} delta={delta:+.2f}"
        )

        result = BenchmarkResult(
            delta_vs_baseline=delta,
            champion_fitness=champion_fitness,
            passed=passed,
            notes=notes,
            ts_ns=ts_ns,
        )
        _logger.debug(
            "BenchmarkEngine[%s] delta=%+.2f passed=%s",
            record.proposal_id[:16],
            delta,
            passed,
        )
        return result

    def _get_champion_fitness(self) -> tuple[float, str]:
        """Return (champion_fitness, notes_prefix) — never raises."""
        try:
            from simulation.dominance_runtime import get_simulation_dominance_runtime
            runtime = get_simulation_dominance_runtime()
            snap = runtime.snapshot()
            dominant = snap.get("dominant_strategy")
            if dominant:
                scoreboard = snap.get("scoreboard", {})
                rec = scoreboard.get(dominant, {})
                fitness = rec.get("best_fitness", 50.0)
                return float(fitness), "dominance_runtime"
        except Exception as exc:
            _logger.debug("BenchmarkEngine: dominance_runtime unavailable (%s)", exc)

        # Synthetic baseline — use a fixed baseline of 50.0
        return 50.0, "synthetic_baseline"

    @property
    def bench_count(self) -> int:
        return self._bench_count


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: BenchmarkEngine | None = None
_engine_lock = threading.Lock()


def get_benchmark_engine(
    *, min_delta: float = BENCHMARK_MIN_DELTA
) -> BenchmarkEngine:
    """Return the process-wide BenchmarkEngine singleton."""
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = BenchmarkEngine(min_delta=min_delta)
    return _engine


__all__ = ["BenchmarkEngine", "BENCHMARK_MIN_DELTA", "get_benchmark_engine"]
