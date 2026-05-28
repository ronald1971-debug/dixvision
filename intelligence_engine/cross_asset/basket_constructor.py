"""XAS-04 — synthetic basket builder.

Builds a weighted synthetic basket from constituent assets.
Pure value objects. INV-15. B1 compliant.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["BasketWeight", "SyntheticBasket", "BasketConstructor"]


@dataclass(frozen=True, slots=True)
class BasketWeight:
    symbol: str
    weight: float  # 0.0–1.0, weights must sum to 1.0


@dataclass(frozen=True, slots=True)
class SyntheticBasket:
    basket_id: str
    weights: tuple[BasketWeight, ...]
    description: str = ""

    def price(self, marks: dict[str, float]) -> float:
        """Compute basket price from constituent marks. Pure."""
        return sum(w.weight * marks.get(w.symbol, 0.0) for w in self.weights)


class BasketConstructor:
    """Build and cache synthetic baskets."""

    def __init__(self) -> None:
        self._baskets: dict[str, SyntheticBasket] = {}

    def build(
        self,
        basket_id: str,
        weights: dict[str, float],
        *,
        description: str = "",
        normalize: bool = True,
    ) -> SyntheticBasket:
        total = sum(weights.values()) or 1.0
        normed = {s: w / total for s, w in weights.items()} if normalize else weights
        basket = SyntheticBasket(
            basket_id=basket_id,
            weights=tuple(
                BasketWeight(symbol=s, weight=w)
                for s, w in sorted(normed.items())
            ),
            description=description,
        )
        self._baskets[basket_id] = basket
        return basket

    def get(self, basket_id: str) -> SyntheticBasket | None:
        return self._baskets.get(basket_id)

    def all_baskets(self) -> tuple[SyntheticBasket, ...]:
        return tuple(self._baskets.values())
