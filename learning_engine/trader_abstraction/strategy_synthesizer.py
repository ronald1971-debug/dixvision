"""Strategy synthesizer — combines strategy atoms into new hybrids.

This is the key layer between extraction and validation: rather than
copying individual trader strategies, the synthesizer recombines atoms
from multiple traders into novel compositions.

From 3 traders:
  Trader A → breakout entry logic
  Trader B → volatility filter
  Trader C → risk model

Synthesizer builds:
  → new hybrid strategy (breakout + vol filter + risk model)

Pure function — no IO, no clock reads (INV-15).
No cross-engine imports (L2) — uses protocol-compatible local types.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class AtomCategory(StrEnum):
    """Strategy atom category (learning-engine local mirror)."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"
    SIZING = "SIZING"
    TIMING = "TIMING"
    FILTER = "FILTER"
    RISK = "RISK"


class StrategyAtomLike(Protocol):
    """Protocol for strategy atoms accepted by the synthesizer.

    Compatible with ``intelligence_engine.trader_modeling.strategy_extractor.StrategyAtom``
    without importing it (L2 isolation).
    """

    @property
    def atom_id(self) -> str: ...

    @property
    def category(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def source_trader(self) -> str: ...

    @property
    def applicable_regimes(self) -> tuple[str, ...]: ...

    @property
    def confidence(self) -> float: ...

    @property
    def parameters(self) -> dict[str, float]: ...


@dataclass(frozen=True, slots=True)
class SynthesizedStrategy:
    """A novel strategy composed from multiple trader atoms.

    Each slot (entry, exit, sizing, filter, risk, timing) can come
    from a different trader source. The synthesizer fills each slot
    from the highest-confidence available atom.
    """

    strategy_id: str
    entry_atom: StrategyAtomLike | None = None
    exit_atom: StrategyAtomLike | None = None
    sizing_atom: StrategyAtomLike | None = None
    filter_atom: StrategyAtomLike | None = None
    risk_atom: StrategyAtomLike | None = None
    timing_atom: StrategyAtomLike | None = None
    composite_confidence: float = 0.0
    source_traders: tuple[str, ...] = ()
    applicable_regimes: tuple[str, ...] = ()
    ts_ns: int = 0

    @property
    def slot_count(self) -> int:
        """Number of filled strategy slots."""
        return sum(
            1
            for a in (
                self.entry_atom,
                self.exit_atom,
                self.sizing_atom,
                self.filter_atom,
                self.risk_atom,
                self.timing_atom,
            )
            if a is not None
        )


@dataclass
class SynthesisReport:
    """Summary of a synthesis batch run."""

    strategies_produced: int = 0
    atoms_consumed: int = 0
    unique_traders: int = 0
    avg_confidence: float = 0.0
    regime_coverage: dict[str, int] = field(default_factory=dict)


class StrategySynthesizer:
    """Recombines strategy atoms from multiple traders into hybrids.

    The synthesizer groups atoms by applicable regime, then fills
    strategy slots from the highest-confidence atoms across traders.
    This produces novel strategies that no single trader would have
    created — the real edge.

    Constraints:
    - Minimum 2 different source traders per strategy (no single-source copies)
    - Entry atom is required (no strategy without an entry signal)
    - Atoms must share at least one applicable regime
    """

    def __init__(
        self,
        *,
        min_sources: int = 2,
        min_confidence: float = 0.3,
    ) -> None:
        self._min_sources = min_sources
        self._min_confidence = min_confidence

    def synthesize(
        self,
        atoms: list[StrategyAtomLike],
        *,
        ts_ns: int = 0,
    ) -> list[SynthesizedStrategy]:
        """Synthesize hybrid strategies from a pool of atoms.

        Groups atoms by regime overlap, then fills slots from the
        highest-confidence atoms per category. Only produces strategies
        with atoms from >= min_sources distinct traders.
        """
        if not atoms:
            return []

        # Collect all regimes
        all_regimes: set[str] = set()
        for atom in atoms:
            all_regimes.update(atom.applicable_regimes)

        strategies: list[SynthesizedStrategy] = []

        # For each regime, build a composite strategy
        for regime in sorted(all_regimes):
            # Filter atoms applicable to this regime
            regime_atoms: dict[str, list[StrategyAtomLike]] = {}
            for atom in atoms:
                if regime in atom.applicable_regimes or "ALL" in atom.applicable_regimes:
                    raw = atom.category
                    cat = raw.upper() if hasattr(raw, "upper") else str(raw).upper()
                    regime_atoms.setdefault(cat, []).append(atom)

            # Need at least an entry atom
            if "ENTRY" not in regime_atoms:
                continue

            # Pick best atom per slot, preferring diverse sources
            slots: dict[str, StrategyAtomLike] = {}
            used_traders: set[str] = set()

            # Entry first (required)
            entry_candidates = sorted(
                regime_atoms["ENTRY"],
                key=lambda a: a.confidence,
                reverse=True,
            )
            if not entry_candidates:
                continue
            slots["ENTRY"] = entry_candidates[0]
            used_traders.add(entry_candidates[0].source_trader)

            # Fill remaining slots, preferring different traders
            for cat in ("EXIT", "SIZING", "FILTER", "RISK", "TIMING"):
                candidates = regime_atoms.get(cat, [])
                if not candidates:
                    continue
                # Prefer atoms from traders not yet used
                diverse = [a for a in candidates if a.source_trader not in used_traders]
                best = diverse[0] if diverse else candidates[0]
                if best.confidence >= self._min_confidence:
                    slots[cat] = best
                    used_traders.add(best.source_trader)

            # Enforce minimum source diversity
            if len(used_traders) < self._min_sources:
                continue

            # Compute composite confidence
            confidences = [a.confidence for a in slots.values()]
            composite = sum(confidences) / len(confidences) if confidences else 0.0

            # Generate deterministic ID
            id_input = f"{regime}:{'|'.join(sorted(a.atom_id for a in slots.values()))}"
            strategy_id = f"synth_{hashlib.blake2b(id_input.encode(), digest_size=8).hexdigest()}"

            strategies.append(
                SynthesizedStrategy(
                    strategy_id=strategy_id,
                    entry_atom=slots.get("ENTRY"),
                    exit_atom=slots.get("EXIT"),
                    sizing_atom=slots.get("SIZING"),
                    filter_atom=slots.get("FILTER"),
                    risk_atom=slots.get("RISK"),
                    timing_atom=slots.get("TIMING"),
                    composite_confidence=composite,
                    source_traders=tuple(sorted(used_traders)),
                    applicable_regimes=(regime,),
                    ts_ns=ts_ns,
                )
            )

        return strategies

    def report(self, strategies: list[SynthesizedStrategy]) -> SynthesisReport:
        """Generate a summary report of synthesized strategies."""
        if not strategies:
            return SynthesisReport()

        all_traders: set[str] = set()
        total_conf = 0.0
        regime_counts: dict[str, int] = {}
        total_atoms = 0

        for s in strategies:
            all_traders.update(s.source_traders)
            total_conf += s.composite_confidence
            total_atoms += s.slot_count
            for r in s.applicable_regimes:
                regime_counts[r] = regime_counts.get(r, 0) + 1

        return SynthesisReport(
            strategies_produced=len(strategies),
            atoms_consumed=total_atoms,
            unique_traders=len(all_traders),
            avg_confidence=total_conf / len(strategies),
            regime_coverage=regime_counts,
        )
