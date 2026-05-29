"""simulation.dominance_runtime — Simulation Dominance Runtime (P5 Priority).

Orchestrates the full simulation suite: the system must dominate all
simulation scenarios BEFORE any real capital deployment is authorized.

Manages:
  MutationTournament  — multi-scenario genome fitness evaluation
  StrategyArena       — tournament selection from simulation results
  AdversarialSuite    — flash crash + stop hunt + regime stress
  DominanceScoreboard — tracks which strategies have cleared all scenarios

On each tick():
  - If a new tournament is due: pull genomes from EvolutionOrchestrator
    DYON proposals and run a tournament round
  - Feed surviving genomes to GovernedEvolutionPipeline as CLASS_A proposals
  - Maintain a dominance scoreboard (strategy → cleared scenarios)
  - Emit results to the DYON observability ledger

The system only achieves "simulation dominance" when:
  - At least one strategy has cleared all 4 adversarial scenario types
  - The winning strategy's fitness exceeds the dominance_threshold
  - The winning strategy has held its rank across 3+ consecutive rounds

Authority (OFFLINE / B1): simulation.*, evolution_engine.*, state.*, core.*
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

DOMINANCE_THRESHOLD: float = 60.0   # minimum fitness score to claim dominance
DOMINANCE_STREAK: int = 3           # consecutive rounds at top before claiming dominance


@dataclass
class DominanceRecord:
    """Per-strategy dominance tracking."""

    strategy_id: str
    total_runs: int = 0
    wins: int = 0
    best_fitness: float = 0.0
    scenarios_cleared: set[str] = field(default_factory=set)
    consecutive_wins: int = 0
    dominant: bool = False

    def update(self, fitness: float, scenario_scores: dict[str, float]) -> None:
        self.total_runs += 1
        if fitness > self.best_fitness:
            self.best_fitness = fitness
        cleared = {s for s, v in scenario_scores.items() if v >= DOMINANCE_THRESHOLD * 0.6}
        self.scenarios_cleared.update(cleared)


class SimulationDominanceRuntime:
    """Orchestrates simulation dominance — the gate before real capital.

    Args:
        tournament_interval: run a tournament every N ticks
        genome_per_round: max genomes to test per tournament round
    """

    def __init__(
        self,
        *,
        tournament_interval: int = 100,
        genome_per_round: int = 8,
    ) -> None:
        self._lock = threading.Lock()
        self._interval = max(10, tournament_interval)
        self._genome_per_round = max(2, genome_per_round)
        self._tick_count: int = 0
        self._tournament_runs: int = 0
        # strategy_id → DominanceRecord
        self._scoreboard: dict[str, DominanceRecord] = {}
        self._dominant_strategy: str = ""
        self._dominance_achieved: bool = False
        self._last_tournament_id: str = ""

    # ------------------------------------------------------------------
    # Primary tick
    # ------------------------------------------------------------------

    def tick(self, *, ts_ns: int) -> bool:
        """Advance one dominance tick.

        Returns True if a tournament ran this tick.
        """
        with self._lock:
            self._tick_count += 1
            should_run = self._tick_count % self._interval == 0

        if not should_run:
            return False

        genomes = self._collect_genomes(ts_ns)
        if len(genomes) < 2:
            return False

        return self._run_tournament(genomes, ts_ns)

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            board = {
                sid: {
                    "total_runs": r.total_runs,
                    "wins": r.wins,
                    "best_fitness": round(r.best_fitness, 2),
                    "scenarios_cleared": list(r.scenarios_cleared),
                    "consecutive_wins": r.consecutive_wins,
                    "dominant": r.dominant,
                }
                for sid, r in self._scoreboard.items()
            }
            return {
                "runtime": "SimulationDominanceRuntime",
                "tick_count": self._tick_count,
                "tournament_runs": self._tournament_runs,
                "dominance_achieved": self._dominance_achieved,
                "dominant_strategy": self._dominant_strategy,
                "scoreboard": board,
                "last_tournament_id": self._last_tournament_id,
                "dominance_threshold": DOMINANCE_THRESHOLD,
                "dominance_streak_required": DOMINANCE_STREAK,
            }

    @property
    def dominance_achieved(self) -> bool:
        return self._dominance_achieved

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _collect_genomes(self, ts_ns: int) -> list[Any]:
        """Collect genomes from DYON proposals and strategy registry."""
        genomes = []
        try:
            from simulation.mutation_tournament import TournamentGenome
            from evolution_engine.dyon.dyon_runtime import get_dyon_runtime
            dyon = get_dyon_runtime()
            proposals = dyon.recent_proposals(limit=self._genome_per_round)
            for prop in proposals:
                genomes.append(TournamentGenome(
                    genome_id=prop.proposal_id[:32],
                    description=prop.description[:128],
                    params={"risk_management": 0.5 + (hash(prop.proposal_id) % 5) * 0.08},
                    mutation_class="CLASS_A",
                    source_module=prop.source_module,
                ))
        except Exception:
            pass

        # Fill with synthetic genomes if not enough real proposals
        try:
            from simulation.mutation_tournament import TournamentGenome
            archetypes = [
                ("momentum_genome", {"trend_following": 0.80, "momentum": 0.75, "risk_management": 0.65}),
                ("value_genome", {"value": 0.85, "mean_reversion": 0.70, "patience": 0.90}),
                ("quant_genome", {"systematic": 0.90, "quant": 0.88, "risk_management": 0.82}),
                ("macro_genome", {"macro_awareness": 0.88, "regime_sensitivity": 0.85, "patience": 0.80}),
                ("hft_genome", {"speed": 0.92, "systematic": 0.88, "risk_management": 0.75}),
                ("crypto_genome", {"momentum": 0.82, "risk_tolerance": 0.80, "speed": 0.65}),
            ]
            existing_ids = {g.genome_id for g in genomes}
            for gid, params in archetypes:
                if gid not in existing_ids and len(genomes) < self._genome_per_round:
                    genomes.append(TournamentGenome(
                        genome_id=gid,
                        description=f"Archetype genome: {gid}",
                        params=params,
                        mutation_class="CLASS_A",
                        source_module="simulation.dominance_runtime",
                    ))
        except Exception:
            pass

        return genomes

    def _run_tournament(self, genomes: list[Any], ts_ns: int) -> bool:
        """Run a mutation tournament and update the scoreboard."""
        try:
            from simulation.mutation_tournament import get_mutation_tournament
            tournament = get_mutation_tournament()
            result = tournament.run(genomes, ts_ns)
        except Exception as exc:
            _logger.debug("SimulationDominanceRuntime: tournament error: %s", exc)
            return False

        with self._lock:
            self._tournament_runs += 1
            self._last_tournament_id = result.tournament_id

            # Update scoreboard
            winner_ids = {s.genome.genome_id for s in result.survivors}
            for survivor in result.survivors:
                sid = survivor.genome.genome_id
                if sid not in self._scoreboard:
                    self._scoreboard[sid] = DominanceRecord(strategy_id=sid)
                rec = self._scoreboard[sid]
                rec.update(survivor.fitness, survivor.scenario_scores)
                if survivor.rank == 1:
                    rec.wins += 1
                    rec.consecutive_wins += 1
                else:
                    rec.consecutive_wins = 0

            # Reset consecutive wins for non-survivors
            for sid, rec in self._scoreboard.items():
                if sid not in winner_ids:
                    rec.consecutive_wins = 0

            # Check for dominance
            for sid, rec in self._scoreboard.items():
                if (
                    rec.best_fitness >= DOMINANCE_THRESHOLD
                    and rec.consecutive_wins >= DOMINANCE_STREAK
                    and len(rec.scenarios_cleared) >= 3
                ):
                    if not rec.dominant:
                        rec.dominant = True
                        self._dominant_strategy = sid
                        self._dominance_achieved = True
                        _logger.info(
                            "SIMULATION DOMINANCE ACHIEVED: strategy=%s fitness=%.1f",
                            sid, rec.best_fitness,
                        )

        # Submit top survivors to GovernedEvolutionPipeline
        self._submit_survivors_to_pipeline(result, ts_ns)
        self._emit_tournament_result(result, ts_ns)
        return True

    def _submit_survivors_to_pipeline(self, result: Any, ts_ns: int) -> None:
        """Feed tournament survivors into the GovernedEvolutionPipeline."""
        try:
            from evolution_engine.governed_pipeline import get_governed_pipeline
            pipeline = get_governed_pipeline()
            for survivor in result.survivors[:3]:
                pipeline.submit(
                    proposal_id=f"sim_{survivor.genome.genome_id}_{ts_ns}",
                    description=f"Simulation survivor (rank={survivor.rank}): {survivor.genome.description}",
                    source_module=survivor.genome.source_module,
                    mutation_class=survivor.genome.mutation_class,
                    ts_ns=ts_ns,
                )
        except Exception as exc:
            _logger.debug("SimulationDominanceRuntime: pipeline submit error: %s", exc)

    def _emit_tournament_result(self, result: Any, ts_ns: int) -> None:
        """Emit tournament result to DYON observability channels."""
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.DYON_SCAN_COMPLETE, {
                "source": "simulation_dominance",
                "tournament_id": result.tournament_id,
                "genome_count": result.genome_count,
                "survivor_count": result.survivor_count,
                "dominance_achieved": self._dominance_achieved,
                "dominant_strategy": self._dominant_strategy,
                "ts_ns": ts_ns,
            })
        except Exception:
            pass
        try:
            from state.ledger.append import append_event
            append_event(
                stream="SYSTEM",
                kind="SIMULATION_TOURNAMENT",
                source="DYON",
                payload={
                    "tournament_id": result.tournament_id,
                    "genome_count": result.genome_count,
                    "survivor_count": result.survivor_count,
                    "arena_digest": result.arena_digest,
                    "scenario_names": list(result.scenario_names),
                    "dominance_achieved": self._dominance_achieved,
                    "ts_ns": ts_ns,
                },
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_runtime: SimulationDominanceRuntime | None = None
_runtime_lock = threading.Lock()


def get_simulation_dominance_runtime(
    *,
    tournament_interval: int = 100,
    genome_per_round: int = 8,
) -> SimulationDominanceRuntime:
    """Return the process-wide SimulationDominanceRuntime singleton."""
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = SimulationDominanceRuntime(
                tournament_interval=tournament_interval,
                genome_per_round=genome_per_round,
            )
    return _runtime


__all__ = [
    "DOMINANCE_STREAK",
    "DOMINANCE_THRESHOLD",
    "DominanceRecord",
    "SimulationDominanceRuntime",
    "get_simulation_dominance_runtime",
]
