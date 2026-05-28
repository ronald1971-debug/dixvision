"""MistakeClassifier — categorizes trading errors for learning.

Every loss is categorized into a mistake type so the learning loop
can target specific weaknesses. Categories:

- SIGNAL_ERROR: bad signal, no edge existed
- TIMING_ERROR: edge existed but entered too early/late
- SIZING_ERROR: direction right but size too large/small
- REGIME_ERROR: strategy invalid for current regime
- EXECUTION_ERROR: strategy right but execution failed
- RISK_ERROR: position violated risk limits
- CORRELATION_ERROR: hidden correlation caused loss
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MistakeCategory(StrEnum):
    SIGNAL_ERROR = "SIGNAL_ERROR"
    TIMING_ERROR = "TIMING_ERROR"
    SIZING_ERROR = "SIZING_ERROR"
    REGIME_ERROR = "REGIME_ERROR"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    RISK_ERROR = "RISK_ERROR"
    CORRELATION_ERROR = "CORRELATION_ERROR"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class MistakeRecord:
    """Classified trading mistake."""

    trade_id: str
    category: MistakeCategory
    confidence: float  # how sure we are of the classification
    description: str
    suggested_fix: str


class MistakeClassifier:
    """Classifies losing trades into error categories.

    Rules-based classifier (deterministic, INV-15). Future versions
    may use ML, but the initial implementation is transparent.
    """

    def classify(
        self,
        *,
        trade_id: str,
        pnl_bps: float,
        direction_correct: bool,
        regime_correct: bool,
        execution_fill_ratio: float,
        entry_slippage_bps: float,
        exit_slippage_bps: float,
        position_size_vs_target: float,  # ratio: actual/intended
        correlated_losses: int,  # how many correlated positions also lost
    ) -> MistakeRecord:
        """Classify a losing trade."""
        # Not a mistake if profitable
        if pnl_bps >= 0:
            return MistakeRecord(
                trade_id=trade_id,
                category=MistakeCategory.UNKNOWN,
                confidence=0.0,
                description="Trade was profitable, no mistake to classify.",
                suggested_fix="N/A",
            )

        # Check in priority order
        if not regime_correct:
            return MistakeRecord(
                trade_id=trade_id,
                category=MistakeCategory.REGIME_ERROR,
                confidence=0.85,
                description="Strategy was invalid for the current market regime.",
                suggested_fix="Improve regime detection; disable strategy in unfavorable regimes.",
            )

        if not direction_correct:
            return MistakeRecord(
                trade_id=trade_id,
                category=MistakeCategory.SIGNAL_ERROR,
                confidence=0.80,
                description="Signal predicted wrong direction; no edge existed.",
                suggested_fix="Review signal generation; check for signal decay.",
            )

        if execution_fill_ratio < 0.5 or (entry_slippage_bps + exit_slippage_bps) > 20:
            return MistakeRecord(
                trade_id=trade_id,
                category=MistakeCategory.EXECUTION_ERROR,
                confidence=0.75,
                description="Direction was correct but execution quality was poor.",
                suggested_fix="Improve execution algorithm; reduce slippage via smarter routing.",
            )

        if abs(position_size_vs_target - 1.0) > 0.3:
            return MistakeRecord(
                trade_id=trade_id,
                category=MistakeCategory.SIZING_ERROR,
                confidence=0.70,
                description="Position size deviated significantly from target.",
                suggested_fix="Review position sizing model; check liquidity constraints.",
            )

        if correlated_losses >= 3:
            return MistakeRecord(
                trade_id=trade_id,
                category=MistakeCategory.CORRELATION_ERROR,
                confidence=0.75,
                description="Multiple correlated positions lost simultaneously.",
                suggested_fix="Add correlation monitoring; diversify exposure.",
            )

        # Direction correct but lost → timing
        return MistakeRecord(
            trade_id=trade_id,
            category=MistakeCategory.TIMING_ERROR,
            confidence=0.60,
            description="Edge existed but entry/exit timing was suboptimal.",
            suggested_fix="Improve entry timing signals; adjust holding period.",
        )
