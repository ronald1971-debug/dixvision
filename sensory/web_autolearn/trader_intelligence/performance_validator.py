"""TI-ING-04 — trader performance validator.

Validates and scores claimed trading performance from self-reported
or crawled P&L data. Pure computation. INV-15. B1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["PerformanceClaim", "ValidationResult", "PerformanceValidator"]


@dataclass(frozen=True, slots=True)
class PerformanceClaim:
    source_id: str
    ts_ns: int
    return_pct: float       # claimed total return %
    win_rate: float         # claimed win rate [0, 1]
    trade_count: int        # number of trades claimed
    drawdown_pct: float     # claimed max drawdown %


@dataclass(frozen=True, slots=True)
class ValidationResult:
    source_id: str
    ts_ns: int
    credibility_score: float   # [0, 1]
    flags: tuple[str, ...]
    passed: bool


_UNREALISTIC_RETURN = 10_000.0   # >10,000% is implausible without context
_MIN_TRADE_COUNT = 10            # fewer trades → low statistical confidence
_MAX_WIN_RATE = 0.95             # above this is suspicious


class PerformanceValidator:
    """Heuristic validation of self-reported trader performance claims."""

    def validate(self, claim: PerformanceClaim) -> ValidationResult:
        flags: list[str] = []
        score = 1.0

        if claim.return_pct > _UNREALISTIC_RETURN:
            flags.append(f"IMPLAUSIBLE_RETURN:{claim.return_pct:.0f}pct")
            score -= 0.4

        if claim.win_rate > _MAX_WIN_RATE:
            flags.append(f"SUSPICIOUS_WIN_RATE:{claim.win_rate:.2f}")
            score -= 0.3

        if claim.trade_count < _MIN_TRADE_COUNT:
            flags.append(f"LOW_SAMPLE_SIZE:{claim.trade_count}")
            score -= 0.2

        if claim.drawdown_pct <= 0:
            flags.append("ZERO_DRAWDOWN_CLAIMED")
            score -= 0.2

        if claim.return_pct > 0 and claim.drawdown_pct > 0:
            calmar = claim.return_pct / claim.drawdown_pct
            if calmar > 100:
                flags.append(f"IMPLAUSIBLE_CALMAR:{calmar:.1f}")
                score -= 0.2

        score = max(0.0, min(1.0, score))
        passed = score >= 0.5 and not any(f.startswith("IMPLAUSIBLE") for f in flags)
        return ValidationResult(
            source_id=claim.source_id,
            ts_ns=claim.ts_ns,
            credibility_score=score,
            flags=tuple(flags),
            passed=passed,
        )
