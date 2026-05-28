"""Strategy composer (BUILD-DIRECTIVE §20).

The ONLY module that may construct :class:`ComposedStrategy` (B-COMPOSER lint rule).
Combines strategy atoms into regime-aware composite strategies that SURPASS
individual trader approaches through intelligent combination.

The composition principle: extract the best atoms from each trader,
combine them in ways that no single trader would, and validate the
combination against historical regimes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ComposedStrategy:
    """A composed strategy built from multiple strategy atoms.

    ONLY this module (strategy_composer/composer.py) may construct this.
    B-COMPOSER lint rule enforces this invariant.
    """

    strategy_id: str
    name: str
    atoms: tuple[str, ...]  # atom_ids
    source_traders: tuple[str, ...]
    regime_fitness: dict[str, float]  # regime → fitness score
    expected_sharpe: float
    expected_max_drawdown: float
    composition_rationale: str
    ts_ns: int
    version: int = 1


@dataclass(frozen=True, slots=True)
class CompositionRequest:
    """Request to compose a new strategy from atoms."""

    target_regime: str
    max_atoms: int = 5
    min_fitness: float = 0.6
    diversity_weight: float = 0.3


class StrategyComposer:
    """Composes strategy atoms into ComposedStrategy objects.

    This is the only class that constructs ComposedStrategy instances.
    """

    def compose(
        self,
        *,
        atoms: list[dict[str, Any]],
        request: CompositionRequest,
        ts_ns: int,
    ) -> ComposedStrategy | None:
        """Compose a strategy from available atoms.

        Args:
            atoms: Available strategy atoms with metadata.
            request: Composition parameters.
            ts_ns: Timestamp for the composition.

        Returns:
            ComposedStrategy if composition succeeds, None if no valid
            composition could be found.
        """
        if not atoms:
            return None

        # Select top atoms by fitness for target regime
        scored = []
        for atom in atoms:
            regime_fit = atom.get("regime_fitness", {}).get(request.target_regime, 0.0)
            if regime_fit >= request.min_fitness:
                scored.append((atom, regime_fit))

        scored.sort(key=lambda x: x[1], reverse=True)
        selected = scored[: request.max_atoms]

        if not selected:
            return None

        atom_ids = tuple(a[0].get("atom_id", "") for a in selected)
        source_traders = tuple({a[0].get("source_trader", "") for a in selected})

        # Compute expected metrics from atom combination
        avg_sharpe = sum(a[0].get("sharpe", 0.0) for a in selected) / len(selected)
        max_dd = max(a[0].get("max_drawdown", 0.0) for a in selected)

        return ComposedStrategy(
            strategy_id=f"composed_{request.target_regime}_{ts_ns}",
            name=f"Composed-{request.target_regime}-{len(selected)}atoms",
            atoms=atom_ids,
            source_traders=source_traders,
            regime_fitness={request.target_regime: scored[0][1] if scored else 0.0},
            expected_sharpe=avg_sharpe,
            expected_max_drawdown=max_dd,
            composition_rationale=(
                f"Combined {len(selected)} atoms from"
                f" {len(source_traders)} traders for {request.target_regime}"
            ),
            ts_ns=ts_ns,
        )
