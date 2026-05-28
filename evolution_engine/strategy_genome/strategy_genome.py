"""Strategy genome encoding (BUILD-DIRECTIVE §21).

A strategy genome encodes a ComposedStrategy as a mutable sequence of
genes (parameters, atoms, weights) that can undergo genetic operations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Gene:
    """A single gene in a strategy genome."""

    name: str
    value: float
    min_value: float
    max_value: float
    mutation_rate: float = 0.1


@dataclass(frozen=True, slots=True)
class StrategyGenome:
    """Genome representation of a composed strategy."""

    genome_id: str
    strategy_id: str
    genes: tuple[Gene, ...]
    atom_ids: tuple[str, ...]
    fitness: float = 0.0
    generation: int = 0
    parent_ids: tuple[str, ...] = ()

    @property
    def gene_count(self) -> int:
        """Number of genes in this genome."""
        return len(self.genes)

    def get_gene(self, name: str) -> Gene | None:
        """Get a gene by name."""
        for g in self.genes:
            if g.name == name:
                return g
        return None
