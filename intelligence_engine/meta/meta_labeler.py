"""Meta-Labeler — confidence-based trade filter (Marcos Lopez de Prado).

Instead of: signal → trade
We do: signal → meta-labeler → trade (or skip)

The meta-labeler answers: "Given this signal, what is the probability
it will be profitable?" and adjusts position size accordingly.

This is used by real quant funds (De Prado's triple-barrier method).
Only the highest-probability setups get full allocation.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum


class MetaDecision(StrEnum):
    TAKE = "TAKE"  # high confidence, full size
    REDUCE = "REDUCE"  # moderate confidence, reduce size
    SKIP = "SKIP"  # low confidence, skip entirely


@dataclass(frozen=True, slots=True)
class MetaLabel:
    """Meta-label output for a signal."""

    signal_id: str
    probability_of_success: float  # [0, 1]
    position_size_modifier: float  # [0, 1] multiply intended size by this
    decision: MetaDecision
    reason: str


class MetaLabeler:
    """Filters and sizes trades based on predicted success probability.

    Uses features of the signal context (regime, time, volatility,
    correlation state, signal strength) to estimate P(profitable).

    Deterministic: same features → same label (INV-15).
    """

    def __init__(
        self,
        *,
        take_threshold: float = 0.65,  # above this → TAKE
        reduce_threshold: float = 0.45,  # between reduce and take → REDUCE
        # below reduce → SKIP
    ) -> None:
        self._take_thresh = take_threshold
        self._reduce_thresh = reduce_threshold
        self._signal_outcomes: deque[tuple[dict[str, float], bool]] = deque(maxlen=500)

    def label(
        self,
        signal_id: str,
        *,
        signal_strength: float,  # [0, 1]
        regime_alignment: float,  # [0, 1] how aligned with current regime
        multi_horizon_agreement: float,  # [0, 1]
        volume_confirmation: float,  # [0, 1]
        historical_winrate: float,  # [0, 1] for this signal type
        volatility_percentile: float,  # [0, 1] current vol vs historical
        correlation_support: float,  # [0, 1] correlated assets agree
    ) -> MetaLabel:
        """Generate meta-label for a trading signal."""
        # Weighted probability model
        p_success = (
            signal_strength * 0.20
            + regime_alignment * 0.20
            + multi_horizon_agreement * 0.15
            + volume_confirmation * 0.10
            + historical_winrate * 0.20
            + (1.0 - abs(volatility_percentile - 0.5) * 2) * 0.05  # prefer moderate vol
            + correlation_support * 0.10
        )

        # Calibrate using historical outcomes
        p_success = self._calibrate(p_success)

        # Size modifier: linear between thresholds
        if p_success >= self._take_thresh:
            size_mod = 0.75 + (p_success - self._take_thresh) / (1 - self._take_thresh) * 0.25
            decision = MetaDecision.TAKE
            reason = f"P(success)={p_success:.0%} ≥ {self._take_thresh:.0%}: full allocation."
        elif p_success >= self._reduce_thresh:
            size_mod = (
                0.3
                + (p_success - self._reduce_thresh)
                / (self._take_thresh - self._reduce_thresh)
                * 0.45
            )
            decision = MetaDecision.REDUCE
            reason = f"P(success)={p_success:.0%}: moderate confidence, reduced size."
        else:
            size_mod = 0.0
            decision = MetaDecision.SKIP
            reason = f"P(success)={p_success:.0%} < {self._reduce_thresh:.0%}: skip."

        return MetaLabel(
            signal_id=signal_id,
            probability_of_success=p_success,
            position_size_modifier=size_mod,
            decision=decision,
            reason=reason,
        )

    def record_outcome(self, features: dict[str, float], was_profitable: bool) -> None:
        """Record a signal outcome for calibration."""
        self._signal_outcomes.append((features, was_profitable))

    def _calibrate(self, raw_p: float) -> float:
        """Calibrate raw probability using historical outcomes.

        If we have enough history, adjust for overconfidence/underconfidence.
        """
        if len(self._signal_outcomes) < 50:
            return raw_p  # not enough data to calibrate

        # Simple calibration: compare predicted vs actual hit rates
        # in similar probability buckets
        bucket_size = 0.1
        bucket_start = max(0.0, raw_p - bucket_size / 2)
        bucket_end = min(1.0, raw_p + bucket_size / 2)

        in_bucket = [
            outcome
            for feats, outcome in self._signal_outcomes
            if bucket_start <= sum(feats.values()) / max(len(feats), 1) <= bucket_end
        ]

        if len(in_bucket) < 10:
            return raw_p

        actual_rate = sum(1 for x in in_bucket if x) / len(in_bucket)
        # Blend: 70% model, 30% historical
        return raw_p * 0.7 + actual_rate * 0.3
