"""Strategy genome recombination (BUILD-DIRECTIVE §21).

Crossover operations between strategy genomes:
- Uniform crossover: randomly select genes from either parent
- Single-point crossover: split at a point, take left from parent A, right from B
"""

from __future__ import annotations

import random

from evolution_engine.strategy_genome.strategy_genome import StrategyGenome


def crossover_uniform(
    parent_a: StrategyGenome,
    parent_b: StrategyGenome,
    *,
    seed: int | None = None,
) -> StrategyGenome:
    """Uniform crossover — randomly select each gene from either parent.

    Parents must have the same gene structure (same names in same order).
    """
    rng = random.Random(seed)

    if len(parent_a.genes) != len(parent_b.genes):
        msg = "parents must have same gene count for crossover"
        raise ValueError(msg)

    child_genes = []
    for gene_a, gene_b in zip(parent_a.genes, parent_b.genes, strict=True):
        selected = gene_a if rng.random() < 0.5 else gene_b
        child_genes.append(selected)

    return StrategyGenome(
        genome_id=f"child_{parent_a.genome_id}x{parent_b.genome_id}",
        strategy_id=f"recomb_{parent_a.strategy_id}",
        genes=tuple(child_genes),
        atom_ids=parent_a.atom_ids,  # Inherit atom structure from parent A
        fitness=0.0,
        generation=max(parent_a.generation, parent_b.generation) + 1,
        parent_ids=(parent_a.genome_id, parent_b.genome_id),
    )


def crossover_single_point(
    parent_a: StrategyGenome,
    parent_b: StrategyGenome,
    *,
    seed: int | None = None,
) -> StrategyGenome:
    """Single-point crossover — split at random point."""
    rng = random.Random(seed)

    if len(parent_a.genes) != len(parent_b.genes):
        msg = "parents must have same gene count for crossover"
        raise ValueError(msg)

    point = rng.randint(1, len(parent_a.genes) - 1)
    child_genes = list(parent_a.genes[:point]) + list(parent_b.genes[point:])

    return StrategyGenome(
        genome_id=f"child_sp_{parent_a.genome_id}x{parent_b.genome_id}",
        strategy_id=f"recomb_{parent_a.strategy_id}",
        genes=tuple(child_genes),
        atom_ids=parent_a.atom_ids,
        fitness=0.0,
        generation=max(parent_a.generation, parent_b.generation) + 1,
        parent_ids=(parent_a.genome_id, parent_b.genome_id),
    )
