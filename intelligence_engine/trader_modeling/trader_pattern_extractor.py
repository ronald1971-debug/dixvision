"""Trader pattern extractor (BUILD-DIRECTIVE §15 — TIS module 9).

Extracts recurring behavioral patterns from trader observations:
- Entry patterns (when/how they enter)
- Exit patterns (when/how they exit)
- Sizing patterns (how they scale)
- Regime patterns (how they adapt to market conditions)

Patterns are stored in state/memory_tensor/trader_patterns/.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PatternType(StrEnum):
    """Type of trader pattern."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"
    SIZING = "SIZING"
    REGIME_SWITCH = "REGIME_SWITCH"
    RISK_ADJUSTMENT = "RISK_ADJUSTMENT"
    CONVICTION_SCALE = "CONVICTION_SCALE"


@dataclass(frozen=True, slots=True)
class ExtractedPattern:
    """A recurring behavioral pattern extracted from trader data."""

    pattern_id: str
    pattern_type: PatternType
    trader_id: str
    description: str
    frequency: int  # how many times observed
    success_rate: float  # 0-1
    applicable_regimes: tuple[str, ...]
    conditions: dict[str, float]  # condition → threshold
    confidence: float
    last_seen_ts_ns: int


class TraderPatternExtractor:
    """Extracts recurring patterns from trader behavior history.

    Uses frequency analysis to identify what a trader does repeatedly
    and successfully. These patterns become candidate strategy atoms.
    """

    def __init__(self, *, min_frequency: int = 3, min_success: float = 0.5) -> None:
        self._min_frequency = min_frequency
        self._min_success = min_success
        self._pattern_buffer: dict[str, list[dict[str, float]]] = {}

    def observe(
        self,
        *,
        trader_id: str,
        action_type: str,
        regime: str,
        outcome: float,
        conditions: dict[str, float],
        ts_ns: int,
    ) -> None:
        """Record an observation for pattern detection."""
        key = f"{trader_id}:{action_type}:{regime}"
        self._pattern_buffer.setdefault(key, []).append(
            {
                "outcome": outcome,
                "ts_ns": float(ts_ns),
                **conditions,
            }
        )

    def extract(self, trader_id: str, *, ts_ns: int = 0) -> list[ExtractedPattern]:
        """Extract patterns for a trader from accumulated observations."""
        patterns: list[ExtractedPattern] = []
        prefix = f"{trader_id}:"

        for key, observations in self._pattern_buffer.items():
            if not key.startswith(prefix):
                continue
            if len(observations) < self._min_frequency:
                continue

            parts = key.split(":")
            action_type = parts[1] if len(parts) > 1 else "UNKNOWN"
            regime = parts[2] if len(parts) > 2 else "ALL"

            # Calculate success rate
            successes = sum(1 for o in observations if o.get("outcome", 0) > 0)
            success_rate = successes / len(observations)

            if success_rate < self._min_success:
                continue

            # Average conditions across observations
            condition_keys = {k for o in observations for k in o if k not in ("outcome", "ts_ns")}
            avg_conditions = {}
            for ck in condition_keys:
                vals = [o[ck] for o in observations if ck in o]
                if vals:
                    avg_conditions[ck] = sum(vals) / len(vals)

            pattern_type = self._classify_pattern_type(action_type)
            last_ts = max(int(o.get("ts_ns", 0)) for o in observations)

            patterns.append(
                ExtractedPattern(
                    pattern_id=f"pat_{trader_id}_{action_type}_{regime}",
                    pattern_type=pattern_type,
                    trader_id=trader_id,
                    description=f"{action_type} pattern in {regime} regime",
                    frequency=len(observations),
                    success_rate=success_rate,
                    applicable_regimes=(regime,),
                    conditions=avg_conditions,
                    confidence=min(success_rate * (len(observations) / 10.0), 1.0),
                    last_seen_ts_ns=last_ts if last_ts > 0 else ts_ns,
                )
            )

        return patterns

    @staticmethod
    def _classify_pattern_type(action_type: str) -> PatternType:
        """Classify action type into pattern type."""
        action_lower = action_type.lower()
        if "entry" in action_lower or "buy" in action_lower or "long" in action_lower:
            return PatternType.ENTRY
        if "exit" in action_lower or "sell" in action_lower or "close" in action_lower:
            return PatternType.EXIT
        if "size" in action_lower or "scale" in action_lower:
            return PatternType.SIZING
        if "regime" in action_lower or "switch" in action_lower:
            return PatternType.REGIME_SWITCH
        if "risk" in action_lower:
            return PatternType.RISK_ADJUSTMENT
        return PatternType.CONVICTION_SCALE
