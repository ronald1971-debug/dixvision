"""evolution_engine/genetic/fitness_inheritance.py
DIX VISION v42.2 — Fitness Inheritance

Computes inherited fitness scores for child chromosomes derived from
parent chromosomes via crossover and mutation. Fitness inheritance
blends parent scores according to contribution weights and applies a
novelty penalty for chromosomes that diverge too far from proven parents.

Pure functions + frozen dataclasses (INV-15 replay determinism).
No IO, no random, no clock reads — all randomness comes from caller-
supplied crossover/mutation operators.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FitnessRecord:
    """Fitness score record for one chromosome."""
    chromosome_id: str
    fitness: float            # composite fitness score
    sharpe: float
    win_rate: float
    max_drawdown: float
    generation: int
    ts_ns: int


@dataclass(frozen=True, slots=True)
class InheritedFitness:
    """Inherited fitness estimate for a child chromosome."""
    child_id: str
    parent_a_id: str
    parent_b_id: str | None
    inherited_fitness: float
    novelty_penalty: float
    adjusted_fitness: float     # inherited_fitness * (1 - novelty_penalty)
    generation: int
    ts_ns: int


def _euclidean_distance(
    params_a: dict[str, float],
    params_b: dict[str, float],
) -> float:
    """Euclidean distance between two parameter dicts."""
    keys = set(params_a.keys()) | set(params_b.keys())
    return math.sqrt(
        sum((params_a.get(k, 0.0) - params_b.get(k, 0.0)) ** 2 for k in keys)
    )


def _blend_fitness(
    fitness_a: float,
    fitness_b: float,
    weight_a: float,
) -> float:
    """Linearly blend two fitness scores."""
    w = max(0.0, min(1.0, weight_a))
    return w * fitness_a + (1.0 - w) * fitness_b


def compute_novelty_penalty(
    child_params: dict[str, float],
    parent_params: list[dict[str, float]],
    population_params: list[dict[str, float]],
    novelty_threshold: float = 2.0,
) -> float:
    """
    Compute a novelty penalty in [0, 1] based on distance from parents
    and population. High novelty = large distance = higher penalty.

    Penalty = sigmoid((mean_parent_dist - novelty_threshold) / threshold)
    """
    if not parent_params:
        return 0.0
    mean_parent_dist = sum(
        _euclidean_distance(child_params, p) for p in parent_params
    ) / len(parent_params)
    x = (mean_parent_dist - novelty_threshold) / max(novelty_threshold, 1e-8)
    penalty = 1.0 / (1.0 + math.exp(-x))
    return min(1.0, penalty)


def inherit_fitness(
    child_id: str,
    child_params: dict[str, float],
    parent_a: FitnessRecord,
    parent_b: FitnessRecord | None,
    population_params: list[dict[str, float]],
    parent_a_params: dict[str, float],
    parent_b_params: dict[str, float] | None,
    crossover_weight_a: float = 0.5,
    novelty_threshold: float = 2.0,
    ts_ns: int = 0,
) -> InheritedFitness:
    """
    Compute inherited fitness for a child chromosome.

    Args:
        crossover_weight_a: Fraction of parent A's contribution [0, 1].
        novelty_threshold:  Distance beyond which novelty becomes penalised.
    """
    if parent_b is None:
        base_fitness = parent_a.fitness
        parent_params_list = [parent_a_params]
    else:
        base_fitness = _blend_fitness(
            parent_a.fitness,
            parent_b.fitness,
            crossover_weight_a,
        )
        parent_params_list = [parent_a_params, parent_b_params] if parent_b_params else [parent_a_params]

    novelty_penalty = compute_novelty_penalty(
        child_params,
        parent_params_list,
        population_params,
        novelty_threshold,
    )
    adjusted = base_fitness * (1.0 - novelty_penalty * 0.5)  # max 50% novelty penalty

    return InheritedFitness(
        child_id=child_id,
        parent_a_id=parent_a.chromosome_id,
        parent_b_id=parent_b.chromosome_id if parent_b else None,
        inherited_fitness=base_fitness,
        novelty_penalty=novelty_penalty,
        adjusted_fitness=adjusted,
        generation=parent_a.generation + 1,
        ts_ns=ts_ns,
    )


__all__ = [
    "FitnessRecord",
    "InheritedFitness",
    "compute_novelty_penalty",
    "inherit_fitness",
]
