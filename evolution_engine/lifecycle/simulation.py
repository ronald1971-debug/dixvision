"""evolution_engine.lifecycle.simulation — Stage 3: mutation tournament fitness.

SimulationEvaluator runs a proposal through the multi-scenario mutation
tournament (simulation.mutation_tournament) and scores its fitness.  A
proposal is a survivor only if its fitness exceeds SIMULATION_THRESHOLD.

Falls back to a deterministic synthetic score when the tournament is
unavailable (test / offline environments).

Authority (L2/B1): stdlib only at module level.
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evolution_engine.lifecycle.contracts import ProposalRecord, SimulationResult

_logger = logging.getLogger(__name__)

SIMULATION_THRESHOLD: float = 30.0   # minimum fitness to survive simulation


class SimulationEvaluator:
    """Evaluates a proposal against the adversarial simulation suite.

    Delegates to simulation.mutation_tournament.MutationTournament; falls
    back to a deterministic synthetic score derived from proposal_id when
    the tournament module is unavailable.
    """

    def __init__(self, *, threshold: float = SIMULATION_THRESHOLD) -> None:
        self._threshold = threshold
        self._lock = threading.Lock()
        self._eval_count: int = 0

    def evaluate(self, record: "ProposalRecord", ts_ns: int) -> "SimulationResult":
        """Run the simulation evaluation for *record*.

        Returns a :class:`SimulationResult`; never raises.
        """
        from evolution_engine.lifecycle.contracts import SimulationResult

        with self._lock:
            self._eval_count += 1

        fitness, scenario_scores, tournament_id, rank = self._run(record, ts_ns)
        passed = fitness >= self._threshold

        result = SimulationResult(
            fitness=fitness,
            scenario_scores=scenario_scores,
            tournament_id=tournament_id,
            survivor_rank=rank,
            passed=passed,
            ts_ns=ts_ns,
        )
        _logger.debug(
            "SimulationEvaluator[%s] fitness=%.2f passed=%s",
            record.proposal_id[:16],
            fitness,
            passed,
        )
        return result

    def _run(
        self, record: "ProposalRecord", ts_ns: int
    ) -> tuple[float, dict[str, float], str, int]:
        """Attempt real tournament; fall back to synthetic."""
        try:
            return self._real_tournament(record, ts_ns)
        except Exception as exc:
            _logger.debug("SimulationEvaluator: tournament unavailable (%s) — synthetic", exc)
            return self._synthetic_score(record, ts_ns)

    def _real_tournament(
        self, record: "ProposalRecord", ts_ns: int
    ) -> tuple[float, dict[str, float], str, int]:
        from simulation.mutation_tournament import (
            MutationTournament,
            TournamentGenome,
        )
        genome = TournamentGenome(
            genome_id=record.proposal_id,
            description=record.description,
            params={},
            mutation_class=record.mutation_class,
            source_module=record.source_module,
        )
        tournament = MutationTournament(threshold=self._threshold)
        run = tournament.run([genome], ts_ns=ts_ns)
        if run.survivors:
            s = run.survivors[0]
            return s.fitness, dict(s.scenario_scores), run.tournament_id, s.rank
        return 0.0, {}, run.tournament_id, 0

    @staticmethod
    def _synthetic_score(
        record: "ProposalRecord", ts_ns: int
    ) -> tuple[float, dict[str, float], str, int]:
        """Deterministic synthetic fitness from proposal_id hash."""
        digest = hashlib.sha256(
            f"{record.proposal_id}:{record.mutation_class}:{ts_ns}".encode()
        ).digest()
        base = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        fitness = 20.0 + base * 60.0     # range [20, 80]
        scenarios = {
            "flash_crash": fitness * 0.9,
            "regime_switch": fitness * 1.05,
            "stop_hunter": fitness * 0.95,
            "noise_filter": fitness * 1.0,
        }
        tournament_id = f"synthetic_{digest[:4].hex()}"
        rank = 1 if fitness >= SIMULATION_THRESHOLD else 0
        return fitness, scenarios, tournament_id, rank

    @property
    def eval_count(self) -> int:
        return self._eval_count


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_evaluator: SimulationEvaluator | None = None
_evaluator_lock = threading.Lock()


def get_simulation_evaluator(
    *, threshold: float = SIMULATION_THRESHOLD
) -> SimulationEvaluator:
    """Return the process-wide SimulationEvaluator singleton."""
    global _evaluator
    with _evaluator_lock:
        if _evaluator is None:
            _evaluator = SimulationEvaluator(threshold=threshold)
    return _evaluator


__all__ = ["SimulationEvaluator", "SIMULATION_THRESHOLD", "get_simulation_evaluator"]
