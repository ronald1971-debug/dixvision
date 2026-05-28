"""Strategy genome mutation (BUILD-DIRECTIVE §21).

Applies point mutations to strategy genomes:
- Gaussian noise to continuous parameters
- Atom substitution (swap in a different atom with similar function)
- Weight redistribution
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from evolution_engine.strategy_genome.strategy_genome import Gene, StrategyGenome


@dataclass(frozen=True, slots=True)
class MutationRecord:
    """Record of a mutation applied to a genome."""

    genome_id: str
    gene_name: str
    old_value: float
    new_value: float
    mutation_type: str


def mutate_genome(
    genome: StrategyGenome,
    *,
    mutation_rate: float = 0.1,
    seed: int | None = None,
) -> tuple[StrategyGenome, list[MutationRecord]]:
    """Apply point mutations to a genome.

    Args:
        genome: The genome to mutate.
        mutation_rate: Probability of mutating each gene.
        seed: Random seed for deterministic replay (INV-15).

    Returns:
        Tuple of (mutated_genome, list of mutation records).
    """
    rng = random.Random(seed)
    new_genes = []
    records = []

    for gene in genome.genes:
        if rng.random() < mutation_rate:
            # Gaussian mutation within bounds
            delta = rng.gauss(0, gene.mutation_rate * (gene.max_value - gene.min_value))
            new_value = max(gene.min_value, min(gene.max_value, gene.value + delta))
            new_genes.append(
                Gene(
                    name=gene.name,
                    value=new_value,
                    min_value=gene.min_value,
                    max_value=gene.max_value,
                    mutation_rate=gene.mutation_rate,
                )
            )
            records.append(
                MutationRecord(
                    genome_id=genome.genome_id,
                    gene_name=gene.name,
                    old_value=gene.value,
                    new_value=new_value,
                    mutation_type="gaussian_point",
                )
            )
        else:
            new_genes.append(gene)

    mutated = StrategyGenome(
        genome_id=f"{genome.genome_id}_mut{genome.generation + 1}",
        strategy_id=genome.strategy_id,
        genes=tuple(new_genes),
        atom_ids=genome.atom_ids,
        fitness=0.0,  # Reset — needs re-evaluation
        generation=genome.generation + 1,
        parent_ids=(genome.genome_id,),
    )
    return mutated, records
