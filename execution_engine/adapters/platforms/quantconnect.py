"""QuantConnect platform integration (Paper-S5).

Read-only adapter for QuantConnect LEAN backtesting results,
live algorithm signals, and research environment data.

__capability_tier__ = 0
__forbidden_tiers__ = (5,)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__capability_tier__ = 0
__forbidden_tiers__ = (5,)


@dataclass(frozen=True, slots=True)
class QCBacktestResult:
    """QuantConnect backtest result summary."""

    backtest_id: str
    algorithm_name: str
    start_date: str
    end_date: str
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    total_trades: int
    alpha: float
    beta: float
    information_ratio: float


@dataclass(frozen=True, slots=True)
class QCLiveSignal:
    """Signal from a running QuantConnect algorithm."""

    algorithm_id: str
    symbol: str
    side: str
    quantity: float
    order_type: str
    limit_price: float | None
    tag: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class QCAlgorithmState:
    """Current state of a QuantConnect live algorithm."""

    algorithm_id: str
    name: str
    status: str  # "running" | "stopped" | "liquidated"
    equity: float
    holdings_count: int
    unrealized_pnl: float
    realized_pnl: float


class QuantConnectAdapter:
    """Read-only adapter for QuantConnect platform.

    Reads backtest results, live algorithm state, and signals.
    Never submits orders or modifies algorithms.
    """

    def __init__(self, *, user_id: str = "", api_token: str = "") -> None:
        self._user_id = user_id
        self._token = api_token

    def fetch_backtests(self, *, project_id: str = "", limit: int = 10) -> list[QCBacktestResult]:
        """Fetch backtest results from QuantConnect."""
        return []

    def fetch_live_signals(
        self, *, algorithm_id: str = "", since_ts_ns: int = 0
    ) -> list[QCLiveSignal]:
        """Fetch signals from a live algorithm."""
        return []

    def fetch_algorithm_state(self, *, algorithm_id: str) -> QCAlgorithmState | None:
        """Fetch current state of a live algorithm."""
        return None

    def fetch_research_data(
        self, *, symbol: str, resolution: str = "daily", bars: int = 252
    ) -> list[dict[str, Any]]:
        """Fetch historical data from QC research environment."""
        return []
