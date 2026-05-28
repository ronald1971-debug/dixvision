"""Atom registry (BUILD-DIRECTIVE §20).

Central registry of all known strategy atoms extracted from traders.
Atoms are indexed by category, regime, and source trader for fast lookup
during composition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AtomRegistry:
    """Registry of all known strategy atoms."""

    _atoms: dict[str, dict[str, Any]] = field(default_factory=dict)
    _by_category: dict[str, list[str]] = field(default_factory=dict)
    _by_regime: dict[str, list[str]] = field(default_factory=dict)
    _by_trader: dict[str, list[str]] = field(default_factory=dict)

    def register(self, atom_id: str, atom_data: dict[str, Any]) -> None:
        """Register a new atom in the registry."""
        self._atoms[atom_id] = atom_data

        category = atom_data.get("category", "UNKNOWN")
        self._by_category.setdefault(category, []).append(atom_id)

        for regime in atom_data.get("applicable_regimes", ()):
            self._by_regime.setdefault(regime, []).append(atom_id)

        trader = atom_data.get("source_trader", "")
        if trader:
            self._by_trader.setdefault(trader, []).append(atom_id)

    def get_by_regime(self, regime: str) -> list[dict[str, Any]]:
        """Get all atoms applicable to a regime."""
        atom_ids = self._by_regime.get(regime, [])
        return [self._atoms[aid] for aid in atom_ids if aid in self._atoms]

    def get_by_trader(self, trader_id: str) -> list[dict[str, Any]]:
        """Get all atoms from a specific trader."""
        atom_ids = self._by_trader.get(trader_id, [])
        return [self._atoms[aid] for aid in atom_ids if aid in self._atoms]

    @property
    def size(self) -> int:
        """Total atoms registered."""
        return len(self._atoms)
