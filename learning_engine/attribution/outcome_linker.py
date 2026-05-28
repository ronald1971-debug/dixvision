"""Outcome linker — traces pattern → usage → PnL impact.

Closes the feedback loop between learned trader patterns and their
actual trading outcomes. Every pattern that contributes to a trading
decision gets attributed a share of the resulting PnL.

This enables:
- Identifying which trader sources produce profitable patterns
- Rewarding high-value sources with higher credibility
- Detecting and decaying patterns that consistently lose money
- Calculating ROI per trader source for portfolio optimization

Pure state machine — no IO on the hot path (INV-15).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PatternUsage:
    """Record of a pattern being used in a trading decision."""

    pattern_id: str
    decision_id: str
    contribution_weight: float  # how much this pattern influenced the decision
    ts_ns: int


@dataclass(frozen=True, slots=True)
class OutcomeRecord:
    """Realized PnL outcome linked to a trading decision."""

    decision_id: str
    total_pnl: float
    realized_ts_ns: int


@dataclass(frozen=True, slots=True)
class PatternAttribution:
    """Attributed PnL impact for a single pattern."""

    pattern_id: str
    total_attributed_pnl: float
    usage_count: int
    avg_pnl_per_use: float
    win_rate: float
    source_trader_id: str


@dataclass
class SourceROI:
    """Aggregated ROI metrics for a trader source."""

    source_id: str
    total_attributed_pnl: float = 0.0
    pattern_count: int = 0
    usage_count: int = 0
    win_count: int = 0
    loss_count: int = 0

    @property
    def win_rate(self) -> float:
        total = self.win_count + self.loss_count
        return self.win_count / total if total > 0 else 0.0

    @property
    def avg_pnl_per_pattern(self) -> float:
        return self.total_attributed_pnl / self.pattern_count if self.pattern_count > 0 else 0.0


class OutcomeLinker:
    """Links trader patterns to trading outcomes for attribution.

    Flow:
    1. ``record_usage()`` — log when a pattern influences a decision
    2. ``record_outcome()`` — log the realized PnL of a decision
    3. ``attribute()`` — compute per-pattern PnL attribution
    4. ``source_roi()`` — aggregate ROI by trader source
    """

    def __init__(self) -> None:
        self._usages: list[PatternUsage] = []
        self._outcomes: dict[str, OutcomeRecord] = {}
        self._pattern_to_source: dict[str, str] = {}
        self._decision_usages: dict[str, list[PatternUsage]] = defaultdict(list)

    def register_pattern_source(self, pattern_id: str, source_trader_id: str) -> None:
        """Map a pattern to its originating trader source."""
        self._pattern_to_source[pattern_id] = source_trader_id

    def record_usage(self, usage: PatternUsage) -> None:
        """Record that a pattern was used in a trading decision."""
        self._usages.append(usage)
        self._decision_usages[usage.decision_id].append(usage)

    def record_outcome(self, outcome: OutcomeRecord) -> None:
        """Record the realized PnL of a trading decision."""
        self._outcomes[outcome.decision_id] = outcome

    def attribute(self, pattern_id: str) -> PatternAttribution:
        """Compute PnL attribution for a specific pattern."""
        relevant = [u for u in self._usages if u.pattern_id == pattern_id]
        if not relevant:
            return PatternAttribution(
                pattern_id=pattern_id,
                total_attributed_pnl=0.0,
                usage_count=0,
                avg_pnl_per_use=0.0,
                win_rate=0.0,
                source_trader_id=self._pattern_to_source.get(pattern_id, ""),
            )

        total_pnl = 0.0
        wins = 0
        realized_count = 0

        for usage in relevant:
            outcome = self._outcomes.get(usage.decision_id)
            if outcome is None:
                continue
            # Attribute PnL proportional to contribution weight
            all_usages = self._decision_usages[usage.decision_id]
            total_weight = sum(u.contribution_weight for u in all_usages)
            if total_weight > 0:
                share = usage.contribution_weight / total_weight
                attributed = outcome.total_pnl * share
                total_pnl += attributed
                if attributed > 0:
                    wins += 1
                realized_count += 1

        win_rate = wins / realized_count if realized_count > 0 else 0.0

        return PatternAttribution(
            pattern_id=pattern_id,
            total_attributed_pnl=total_pnl,
            usage_count=len(relevant),
            avg_pnl_per_use=total_pnl / len(relevant) if relevant else 0.0,
            win_rate=win_rate,
            source_trader_id=self._pattern_to_source.get(pattern_id, ""),
        )

    def source_roi(self) -> dict[str, SourceROI]:
        """Aggregate ROI metrics by trader source."""
        roi_map: dict[str, SourceROI] = {}

        # Group patterns by source
        source_patterns: dict[str, set[str]] = defaultdict(set)
        for pid, sid in self._pattern_to_source.items():
            source_patterns[sid].add(pid)

        for source_id, patterns in source_patterns.items():
            roi = SourceROI(source_id=source_id, pattern_count=len(patterns))

            for pid in patterns:
                attr = self.attribute(pid)
                roi.total_attributed_pnl += attr.total_attributed_pnl
                roi.usage_count += attr.usage_count
                # Count wins/losses from this pattern's decisions
                for usage in self._usages:
                    if usage.pattern_id != pid:
                        continue
                    outcome = self._outcomes.get(usage.decision_id)
                    if outcome is None:
                        continue
                    if outcome.total_pnl > 0:
                        roi.win_count += 1
                    else:
                        roi.loss_count += 1

            roi_map[source_id] = roi

        return roi_map

    @property
    def usage_count(self) -> int:
        return len(self._usages)

    @property
    def outcome_count(self) -> int:
        return len(self._outcomes)
