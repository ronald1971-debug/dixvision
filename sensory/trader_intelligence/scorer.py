"""Trader reliability scoring (Sensory-S1.D — Tier 4.4).

Scores discovered traders based on historical accuracy of their
public calls, consistency, and risk/reward quality.

__capability_tier__ = 0
__forbidden_tiers__ = (5,)
"""

from __future__ import annotations

from dataclasses import dataclass

__capability_tier__ = 0
__forbidden_tiers__ = (5,)


@dataclass(frozen=True, slots=True)
class CallOutcome:
    """Outcome of a trader's public call."""

    signal_id: str
    trader_id: str
    symbol: str
    side: str
    entry_price: float
    target_price: float
    actual_price_at_target_time: float
    hit_target: bool
    max_adverse: float  # max loss before target time
    time_to_target_ns: int
    ts_ns: int


@dataclass(frozen=True, slots=True)
class TraderScore:
    """Reliability score for a monitored trader."""

    trader_id: str
    total_calls: int
    winning_calls: int
    win_rate: float
    avg_return_pct: float
    avg_risk_reward: float
    consistency_score: float  # 0-1 (low variance = high)
    recency_weight: float  # recent performance weight
    overall_score: float  # composite 0-1
    regime_specialization: str  # best regime
    ts_ns: int


class TraderScorer:
    """Scores traders based on historical call accuracy.

    Tracks all public calls, measures outcomes, and produces
    a composite reliability score for each trader.
    """

    def __init__(self, *, min_calls_for_score: int = 5) -> None:
        self._min_calls = min_calls_for_score
        self._outcomes: dict[str, list[CallOutcome]] = {}
        self._scores: dict[str, TraderScore] = {}

    def record_outcome(self, outcome: CallOutcome) -> None:
        """Record the outcome of a trader's call."""
        if outcome.trader_id not in self._outcomes:
            self._outcomes[outcome.trader_id] = []
        self._outcomes[outcome.trader_id].append(outcome)

    def compute_score(self, trader_id: str, *, ts_ns: int = 0) -> TraderScore | None:
        """Compute reliability score for a trader."""
        outcomes = self._outcomes.get(trader_id, [])
        if len(outcomes) < self._min_calls:
            return None

        total = len(outcomes)
        wins = sum(1 for o in outcomes if o.hit_target)
        win_rate = wins / total if total > 0 else 0.0

        returns = []
        for o in outcomes:
            if o.entry_price > 0:
                ret = (o.actual_price_at_target_time - o.entry_price) / o.entry_price
                if o.side == "short":
                    ret = -ret
                returns.append(ret)

        avg_return = sum(returns) / len(returns) if returns else 0.0

        # Risk/reward (simple: avg win / avg loss)
        win_returns = [r for r in returns if r > 0]
        loss_returns = [abs(r) for r in returns if r < 0]
        avg_win = sum(win_returns) / len(win_returns) if win_returns else 0.0
        avg_loss = sum(loss_returns) / len(loss_returns) if loss_returns else 1.0
        rr = avg_win / avg_loss if avg_loss > 0 else 0.0

        # Consistency (inverse of return variance)
        if len(returns) > 1:
            mean = avg_return
            variance = sum((r - mean) ** 2 for r in returns) / len(returns)
            consistency = 1.0 / (1.0 + variance * 100)
        else:
            consistency = 0.5

        # Composite score
        overall = (
            win_rate * 0.3
            + min(rr / 3.0, 1.0) * 0.3
            + consistency * 0.2
            + min(avg_return * 10, 1.0) * 0.2
        )
        overall = max(0.0, min(1.0, overall))

        score = TraderScore(
            trader_id=trader_id,
            total_calls=total,
            winning_calls=wins,
            win_rate=win_rate,
            avg_return_pct=avg_return * 100,
            avg_risk_reward=rr,
            consistency_score=consistency,
            recency_weight=1.0,
            overall_score=overall,
            regime_specialization="unknown",
            ts_ns=ts_ns,
        )
        self._scores[trader_id] = score
        return score

    def get_top_traders(self, *, limit: int = 10) -> list[TraderScore]:
        """Get top-scored traders."""
        scores = sorted(
            self._scores.values(),
            key=lambda s: s.overall_score,
            reverse=True,
        )
        return scores[:limit]

    def get_score(self, trader_id: str) -> TraderScore | None:
        """Get latest score for a trader."""
        return self._scores.get(trader_id)
