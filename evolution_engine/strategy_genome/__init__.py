"""evolution_engine.strategy_genome — Genetic strategy evolution (BUILD-DIRECTIVE §21).

Extends the existing evolution_engine with genome-based strategy mutation
and recombination. Strategies are encoded as genomes that can be:
- Mutated (parameter drift, atom substitution)
- Recombined (crossover between successful strategies)
- Selected (fitness-based tournament selection)
"""
