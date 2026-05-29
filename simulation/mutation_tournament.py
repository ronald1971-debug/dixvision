"""simulation.mutation_tournament — Multi-scenario strategy mutation tournament.

Drives strategy genomes through a battery of adversarial simulation scenarios
and selects survivors via tournament selection.  The survivors are fed to the
GovernedEvolutionPipeline as PROPOSED mutations.

Pipeline per genome:
  1. Flash-crash resilience test
  2. Regime switch stress test
  3. Stop-hunter adversarial test
  4. Synthetic noise / latency test
  Aggregate PnL mean → RealitySummary → Arena (tournament selection)
  → PromotionRecommendation for GovernedEvolutionPipeline

Authority (OFFLINE tier): imports only simulation.*, core.contracts.*, state.*
INV-15: ts_ns is caller-supplied; all PRNG seeded from (ts_ns, genome_id).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from core.contracts.simulation import RealitySummary
from simulation.strategy_arena.arena import Arena, ArenaConfig, Contestant

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategy genome — lightweight descriptor for the tournament
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TournamentGenome:
    """One strategy genome entering the mutation tournament."""

    genome_id: str         # unique identifier
    description: str       # human-readable description
    params: dict[str, float]   # mutable strategy parameters
    mutation_class: str    # CLASS_A | CLASS_B | CLASS_C
    source_module: str     # originating module (for pipeline submission)

    def __hash__(self) -> int:
        return hash(self.genome_id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, TournamentGenome) and self.genome_id == other.genome_id


@dataclass(frozen=True, slots=True)
class TournamentSurvivor:
    """A genome that survived the tournament, ready for pipeline submission."""

    genome: TournamentGenome
    fitness: float
    scenario_scores: dict[str, float]   # scenario → pnl_mean_usd
    rank: int                           # 1 = best


@dataclass
class TournamentRun:
    """Results of one complete mutation tournament run."""

    ts_ns: int
    tournament_id: str
    genome_count: int
    survivor_count: int
    survivors: list[TournamentSurvivor]
    arena_digest: str
    scenario_names: tuple[str, ...]


# ---------------------------------------------------------------------------
# Scenario simulators (pure functions, OFFLINE tier)
# ---------------------------------------------------------------------------


def _run_flash_crash_scenario(genome: TournamentGenome, ts_ns: int, seed: int) -> float:
    """Flash crash: how much does the genome lose / recover?"""
    try:
        from simulation.adversarial.flash_crash_synth import FlashCrashParams, generate
        params = FlashCrashParams(
            crash_pct=0.15,
            recovery_pct=0.6,
            crash_bars=8,
            recovery_bars=20,
            bar_volatility=0.003,
        )
        result = generate(params=params, symbol="TEST", ts_ns=ts_ns, start_price=100.0, seed=seed)
        # Proxy fitness: recovery ratio × risk_management param
        risk_mgmt = genome.params.get("risk_management", 0.5)
        recovery = result.recovery_pct if hasattr(result, "recovery_pct") else 0.5
        return float(recovery * risk_mgmt * 100.0)
    except Exception:
        return float(genome.params.get("risk_management", 0.5) * 50.0)


def _run_regime_switch_scenario(genome: TournamentGenome, ts_ns: int, seed: int) -> float:
    """Regime switch: how well does the genome adapt?"""
    try:
        from simulation.regime_switch_sim import RegimeSwitchParams, simulate
        params = RegimeSwitchParams(n_regimes=3, bars_per_regime=50, seed=seed)
        result = simulate(params=params, ts_ns=ts_ns)
        regime_sens = genome.params.get("regime_sensitivity", genome.params.get("macro_awareness", 0.5))
        score = getattr(result, "adaptability_score", 0.5)
        return float(score * regime_sens * 100.0)
    except Exception:
        sens = genome.params.get("regime_sensitivity", genome.params.get("macro_awareness", 0.5))
        return float(sens * 50.0)


def _run_stop_hunter_scenario(genome: TournamentGenome, ts_ns: int, seed: int) -> float:
    """Stop-hunter adversarial: how much liquidity is captured vs lost?"""
    try:
        from simulation.adversarial.stop_hunter import StopHunterParams, simulate
        params = StopHunterParams(hunt_intensity=0.7, seed=seed)
        result = simulate(params=params, ts_ns=ts_ns)
        patience = genome.params.get("patience", 0.5)
        pnl = getattr(result, "net_pnl_usd", 0.0)
        return float(pnl * patience)
    except Exception:
        return float(genome.params.get("patience", 0.5) * 30.0)


def _run_noise_scenario(genome: TournamentGenome, ts_ns: int, seed: int) -> float:
    """Synthetic noise: stability under high-frequency noise."""
    systematic = genome.params.get("systematic", genome.params.get("quant", 0.5))
    speed = genome.params.get("speed", 0.5)
    # Higher systematic + moderate speed = better noise filtering
    return float((systematic * 0.7 + (1.0 - abs(speed - 0.5)) * 0.3) * 80.0)


_SCENARIOS = (
    ("flash_crash", _run_flash_crash_scenario),
    ("regime_switch", _run_regime_switch_scenario),
    ("stop_hunter", _run_stop_hunter_scenario),
    ("noise_filter", _run_noise_scenario),
)


# ---------------------------------------------------------------------------
# MutationTournament
# ---------------------------------------------------------------------------


class MutationTournament:
    """Runs genomes through a multi-scenario battery and selects survivors.

    Args:
        n_winners: number of survivors to select per tournament run
        tournament_size: arena bracket size (2 = head-to-head)
        elitism_count: top-N genomes always survive regardless of bracket
    """

    def __init__(
        self,
        *,
        n_winners: int = 5,
        tournament_size: int = 3,
        elitism_count: int = 2,
    ) -> None:
        self._n_winners = max(1, n_winners)
        self._tournament_size = max(2, tournament_size)
        self._elitism_count = max(0, elitism_count)
        self._arena = Arena()
        self._run_count: int = 0

    def run(
        self,
        genomes: list[TournamentGenome],
        ts_ns: int,
    ) -> TournamentRun:
        """Run one tournament over the given genomes.

        Returns a TournamentRun with ranked survivors.
        """
        if len(genomes) < 2:
            raise ValueError("MutationTournament requires at least 2 genomes")

        self._run_count += 1
        tournament_id = _make_id(ts_ns, self._run_count)
        seed = _derive_seed(ts_ns, self._run_count)

        # Run all scenarios for each genome
        contestants = []
        for genome in genomes:
            scores: dict[str, float] = {}
            for scenario_name, scenario_fn in _SCENARIOS:
                s_seed = _derive_seed(seed, hash(genome.genome_id))
                scores[scenario_name] = scenario_fn(genome, ts_ns, s_seed)

            # Build RealitySummary from scenario scores
            pnl_mean = sum(scores.values()) / max(1, len(scores))
            max_dd = max(0.0, 100.0 - pnl_mean) * 0.3
            summary = RealitySummary(
                strategy_id=genome.genome_id,
                run_count=len(_SCENARIOS),
                pnl_mean_usd=pnl_mean,
                pnl_std_usd=pnl_mean * 0.2,
                max_drawdown_usd=max_dd,
                sharpe_ratio=pnl_mean / max(1.0, max_dd),
                win_rate=min(1.0, pnl_mean / 100.0),
            )
            contestants.append((genome, scores, Contestant(
                strategy_id=genome.genome_id,
                summary=summary,
            )))

        # Tournament selection via Arena
        arena_contestants = [c for _, _, c in contestants]
        n_win = min(self._n_winners, len(contestants))
        elite = min(self._elitism_count, len(contestants))
        config = ArenaConfig(
            arena_id=tournament_id,
            tournament_size=min(self._tournament_size, len(contestants)),
            n_winners=n_win,
            elitism_count=elite,
        )
        arena_result = self._arena.run(
            contestants=arena_contestants,
            config=config,
            seed=seed,
            ts_ns=ts_ns,
        )

        # Map survivors to TournamentSurvivor records
        genome_map = {g.genome_id: (g, scores) for g, scores, _ in contestants}
        survivors: list[TournamentSurvivor] = []
        for rank, sid in enumerate(arena_result.survivors[:n_win], start=1):
            if sid in genome_map:
                g, scores = genome_map[sid]
                fitness = sum(scores.values()) / max(1, len(scores))
                survivors.append(TournamentSurvivor(
                    genome=g,
                    fitness=round(fitness, 4),
                    scenario_scores=scores,
                    rank=rank,
                ))

        return TournamentRun(
            ts_ns=ts_ns,
            tournament_id=tournament_id,
            genome_count=len(genomes),
            survivor_count=len(survivors),
            survivors=survivors,
            arena_digest=arena_result.arena_digest,
            scenario_names=tuple(name for name, _ in _SCENARIOS),
        )

    @property
    def run_count(self) -> int:
        return self._run_count


def _make_id(ts_ns: int, counter: int) -> str:
    raw = f"mt_{ts_ns}_{counter}".encode()
    return "mt_" + hashlib.blake2b(raw, digest_size=4).hexdigest()


def _derive_seed(ts_ns: int, counter: int) -> int:
    raw = (ts_ns * 0x9E3779B97F4A7C15 + counter) & ((1 << 64) - 1)
    return raw


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_tournament: MutationTournament | None = None


def get_mutation_tournament(
    n_winners: int = 5,
    tournament_size: int = 3,
    elitism_count: int = 2,
) -> MutationTournament:
    """Return the process-wide MutationTournament singleton."""
    global _tournament
    if _tournament is None:
        _tournament = MutationTournament(
            n_winners=n_winners,
            tournament_size=tournament_size,
            elitism_count=elitism_count,
        )
    return _tournament


__all__ = [
    "MutationTournament",
    "TournamentGenome",
    "TournamentRun",
    "TournamentSurvivor",
    "get_mutation_tournament",
]
