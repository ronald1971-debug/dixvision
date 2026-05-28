"""Composition validator (BUILD-DIRECTIVE §20 — Strategy Composer module 4).

Validates composed strategies before they enter the sandbox/backtest
pipeline. A composed strategy must pass structural, diversity, and
risk checks before promotion_gates.py will consider it.

Validation is BLOCKING — invalid compositions never reach execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ValidationResult(StrEnum):
    """Result of composition validation."""

    VALID = "VALID"
    REJECTED_INSUFFICIENT_ATOMS = "REJECTED_INSUFFICIENT_ATOMS"
    REJECTED_LOW_DIVERSITY = "REJECTED_LOW_DIVERSITY"
    REJECTED_EXCESSIVE_CORRELATION = "REJECTED_EXCESSIVE_CORRELATION"
    REJECTED_MISSING_EXIT = "REJECTED_MISSING_EXIT"
    REJECTED_MISSING_RISK = "REJECTED_MISSING_RISK"
    REJECTED_SINGLE_SOURCE = "REJECTED_SINGLE_SOURCE"
    REJECTED_UNTESTED_ATOMS = "REJECTED_UNTESTED_ATOMS"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Detailed validation report for a composed strategy."""

    strategy_id: str
    result: ValidationResult
    score: float  # 0=worst, 1=best
    checks_passed: tuple[str, ...]
    checks_failed: tuple[str, ...]
    recommendations: tuple[str, ...]


class CompositionValidator:
    """Validates composed strategies for structural soundness.

    A valid composition must:
    1. Have at least min_atoms atoms
    2. Include both entry AND exit logic
    3. Include risk management
    4. Draw from multiple source traders (diversity)
    5. Not have all atoms highly correlated (shared risk)
    6. Have atoms that have been tested (min observations)
    """

    def __init__(
        self,
        *,
        min_atoms: int = 2,
        min_sources: int = 2,
        max_correlation: float = 0.85,
        min_diversity: float = 0.3,
    ) -> None:
        self._min_atoms = min_atoms
        self._min_sources = min_sources
        self._max_correlation = max_correlation
        self._min_diversity = min_diversity

    def validate(
        self,
        *,
        strategy_id: str,
        atom_categories: list[str],
        source_traders: list[str],
        pairwise_correlations: list[float] | None = None,
        diversity_score: float = 0.5,
        atom_observation_counts: list[int] | None = None,
    ) -> ValidationReport:
        """Validate a composed strategy."""
        passed: list[str] = []
        failed: list[str] = []
        recommendations: list[str] = []

        # Check 1: Minimum atoms
        if len(atom_categories) >= self._min_atoms:
            passed.append("min_atoms")
        else:
            failed.append("min_atoms")
            recommendations.append(
                f"Need at least {self._min_atoms} atoms, got {len(atom_categories)}"
            )

        # Check 2: Has exit logic
        has_exit = any(c.upper() in ("EXIT", "TAKE_PROFIT", "STOP_LOSS") for c in atom_categories)
        if has_exit:
            passed.append("has_exit")
        else:
            failed.append("has_exit")
            recommendations.append("Add an exit/take-profit atom")

        # Check 3: Has risk management
        has_risk = any(c.upper() in ("RISK", "SIZING", "RISK_ADJUSTMENT") for c in atom_categories)
        if has_risk:
            passed.append("has_risk")
        else:
            failed.append("has_risk")
            recommendations.append("Add a risk management atom")

        # Check 4: Multiple sources (diversity)
        unique_sources = set(source_traders)
        if len(unique_sources) >= self._min_sources:
            passed.append("source_diversity")
        else:
            failed.append("source_diversity")
            recommendations.append(
                f"Need atoms from {self._min_sources}+ traders, got {len(unique_sources)}"
            )

        # Check 5: Correlation check
        if pairwise_correlations:
            max_corr = max(abs(c) for c in pairwise_correlations)
            if max_corr <= self._max_correlation:
                passed.append("correlation_check")
            else:
                failed.append("correlation_check")
                recommendations.append(
                    f"Max pairwise correlation {max_corr:.2f} exceeds {self._max_correlation}"
                )
        else:
            passed.append("correlation_check")  # skip if no data

        # Check 6: Diversity score
        if diversity_score >= self._min_diversity:
            passed.append("diversity_score")
        else:
            failed.append("diversity_score")
            recommendations.append(f"Diversity {diversity_score:.2f} below {self._min_diversity}")

        # Check 7: Atoms tested
        if atom_observation_counts:
            untested = sum(1 for c in atom_observation_counts if c < 5)
            if untested == 0:
                passed.append("atoms_tested")
            else:
                failed.append("atoms_tested")
                recommendations.append(f"{untested} atoms have <5 observations")
        else:
            passed.append("atoms_tested")

        # Determine result
        if not failed:
            result = ValidationResult.VALID
        elif "min_atoms" in failed:
            result = ValidationResult.REJECTED_INSUFFICIENT_ATOMS
        elif "has_exit" in failed:
            result = ValidationResult.REJECTED_MISSING_EXIT
        elif "has_risk" in failed:
            result = ValidationResult.REJECTED_MISSING_RISK
        elif "source_diversity" in failed:
            result = ValidationResult.REJECTED_SINGLE_SOURCE
        elif "correlation_check" in failed:
            result = ValidationResult.REJECTED_EXCESSIVE_CORRELATION
        elif "diversity_score" in failed:
            result = ValidationResult.REJECTED_LOW_DIVERSITY
        else:
            result = ValidationResult.REJECTED_UNTESTED_ATOMS

        # Score: proportion of checks passed
        total_checks = len(passed) + len(failed)
        score = len(passed) / max(total_checks, 1)

        return ValidationReport(
            strategy_id=strategy_id,
            result=result,
            score=score,
            checks_passed=tuple(passed),
            checks_failed=tuple(failed),
            recommendations=tuple(recommendations),
        )
