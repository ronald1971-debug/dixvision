"""Strategy extractor (BUILD-DIRECTIVE §15 — TIS module 5).

Extracts strategy atoms from trader observations. A strategy atom is
the smallest unit of trading logic that can be:
- Attributed to a specific trader/philosophy
- Tested in isolation via backtest
- Combined with other atoms via strategy_composer

Examples of atoms:
- "Enter long on golden cross (50/200 EMA)" — Livermore trend
- "Scale in on -2σ reversion" — mean reversion
- "Cut loss at 1R, let winners run 3R" — risk management
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AtomCategory(StrEnum):
    """Category of strategy atom."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"
    SIZING = "SIZING"
    TIMING = "TIMING"
    FILTER = "FILTER"
    RISK = "RISK"


@dataclass(frozen=True, slots=True)
class StrategyAtom:
    """Smallest unit of extractable trading logic."""

    atom_id: str
    category: AtomCategory
    description: str
    source_trader: str
    source_philosophy: str
    parameters: dict[str, float]
    applicable_regimes: tuple[str, ...]
    confidence: float
    ts_ns: int


class StrategyExtractor:
    """Extracts strategy atoms from trader content and observations."""

    def extract_from_observation(
        self,
        *,
        trader_id: str,
        philosophy: str,
        content: str,
        ts_ns: int,
    ) -> list[StrategyAtom]:
        """Extract strategy atoms from a trader observation.

        In production, this uses NLP to identify actionable patterns.
        Returns a list of extracted atoms with confidence scores.
        """
        # Placeholder — production uses LLM extraction
        atoms: list[StrategyAtom] = []
        if "trend" in content.lower():
            atoms.append(
                StrategyAtom(
                    atom_id=f"atom_{trader_id}_trend_{ts_ns}",
                    category=AtomCategory.ENTRY,
                    description="Trend-following entry signal",
                    source_trader=trader_id,
                    source_philosophy=philosophy,
                    parameters={"lookback": 20.0, "threshold": 0.5},
                    applicable_regimes=("TRENDING",),
                    confidence=0.6,
                    ts_ns=ts_ns,
                )
            )
        if "risk" in content.lower() or "stop" in content.lower():
            atoms.append(
                StrategyAtom(
                    atom_id=f"atom_{trader_id}_risk_{ts_ns}",
                    category=AtomCategory.RISK,
                    description="Risk management rule",
                    source_trader=trader_id,
                    source_philosophy=philosophy,
                    parameters={"max_risk_pct": 2.0},
                    applicable_regimes=("ALL",),
                    confidence=0.7,
                    ts_ns=ts_ns,
                )
            )
        return atoms
