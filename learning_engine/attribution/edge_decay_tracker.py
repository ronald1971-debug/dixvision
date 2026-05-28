"""EdgeDecayTracker — detects when a trading edge is dying.

Every edge decays over time as markets adapt. This tracker monitors:
- Rolling Sharpe ratio trend
- Win-rate degradation
- Profit factor compression
- Regime-specific performance fade

When an edge is dying, the system should:
1. Reduce allocation
2. Flag for strategy arena
3. Trigger alpha miner to find replacement
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum


class EdgeHealth(StrEnum):
    STRONG = "STRONG"  # edge performing well
    STABLE = "STABLE"  # edge holding but not growing
    WEAKENING = "WEAKENING"  # early decay detected
    DYING = "DYING"  # significant decay, reduce allocation
    DEAD = "DEAD"  # edge no longer exists


@dataclass(frozen=True, slots=True)
class EdgeHealthReport:
    """Health assessment of a strategy's edge."""

    strategy_id: str
    health: EdgeHealth
    sharpe_trend: float  # slope of rolling Sharpe (-1 to 1)
    win_rate_trend: float  # slope of rolling win rate
    profit_factor_trend: float  # slope of rolling PF
    days_since_peak_sharpe: int
    recommendation: str


class EdgeDecayTracker:
    """Monitors edge health for each strategy over time.

    Uses rolling windows to detect performance trends.
    Pure / deterministic (INV-15): same inputs → same health.
    """

    def __init__(self, window: int = 50) -> None:
        self._window = window
        self._sharpe_history: dict[str, deque[float]] = {}
        self._winrate_history: dict[str, deque[float]] = {}
        self._pf_history: dict[str, deque[float]] = {}
        self._peak_sharpe: dict[str, float] = {}
        self._ticks_since_peak: dict[str, int] = {}

    def update(
        self,
        strategy_id: str,
        *,
        sharpe: float,
        win_rate: float,
        profit_factor: float,
    ) -> EdgeHealthReport:
        """Update metrics and assess edge health."""
        if strategy_id not in self._sharpe_history:
            self._sharpe_history[strategy_id] = deque(maxlen=self._window)
            self._winrate_history[strategy_id] = deque(maxlen=self._window)
            self._pf_history[strategy_id] = deque(maxlen=self._window)
            self._peak_sharpe[strategy_id] = sharpe
            self._ticks_since_peak[strategy_id] = 0

        self._sharpe_history[strategy_id].append(sharpe)
        self._winrate_history[strategy_id].append(win_rate)
        self._pf_history[strategy_id].append(profit_factor)

        # Track peak
        if sharpe > self._peak_sharpe[strategy_id]:
            self._peak_sharpe[strategy_id] = sharpe
            self._ticks_since_peak[strategy_id] = 0
        else:
            self._ticks_since_peak[strategy_id] += 1

        # Compute trends
        sharpe_trend = self._trend(self._sharpe_history[strategy_id])
        wr_trend = self._trend(self._winrate_history[strategy_id])
        pf_trend = self._trend(self._pf_history[strategy_id])

        # Classify health
        health = self._classify(
            sharpe_trend,
            wr_trend,
            pf_trend,
            self._ticks_since_peak[strategy_id],
            sharpe,
        )

        recommendation = self._recommend(health, strategy_id)

        return EdgeHealthReport(
            strategy_id=strategy_id,
            health=health,
            sharpe_trend=sharpe_trend,
            win_rate_trend=wr_trend,
            profit_factor_trend=pf_trend,
            days_since_peak_sharpe=self._ticks_since_peak[strategy_id],
            recommendation=recommendation,
        )

    def _trend(self, values: deque[float]) -> float:
        """Simple linear regression slope."""
        n = len(values)
        if n < 5:
            return 0.0
        xs = list(range(n))
        x_mean = sum(xs) / n
        y_mean = sum(values) / n
        num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values, strict=True))
        den = sum((x - x_mean) ** 2 for x in xs)
        return num / den if den > 0 else 0.0

    def _classify(
        self,
        sharpe_trend: float,
        wr_trend: float,
        pf_trend: float,
        ticks_since_peak: int,
        current_sharpe: float,
    ) -> EdgeHealth:
        """Classify edge health from trends."""
        declining_count = sum(
            [
                sharpe_trend < -0.01,
                wr_trend < -0.005,
                pf_trend < -0.02,
            ]
        )

        if current_sharpe < 0 and ticks_since_peak > 30:
            return EdgeHealth.DEAD
        if declining_count >= 3 or (sharpe_trend < -0.05 and ticks_since_peak > 20):
            return EdgeHealth.DYING
        if declining_count >= 2 or ticks_since_peak > 15:
            return EdgeHealth.WEAKENING
        if sharpe_trend > 0.01:
            return EdgeHealth.STRONG
        return EdgeHealth.STABLE

    def _recommend(self, health: EdgeHealth, strategy_id: str) -> str:
        match health:
            case EdgeHealth.DEAD:
                return f"Kill {strategy_id} — edge exhausted. Trigger alpha miner for replacement."
            case EdgeHealth.DYING:
                return f"Reduce {strategy_id} allocation by 50%. Prepare replacement."
            case EdgeHealth.WEAKENING:
                return f"Monitor {strategy_id} closely. Cap allocation growth."
            case EdgeHealth.STABLE:
                return f"Maintain {strategy_id} allocation."
            case EdgeHealth.STRONG:
                return f"Consider scaling {strategy_id} allocation."
