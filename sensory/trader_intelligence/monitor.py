"""Trader monitoring pipeline (Sensory-S1.D — Tier 4.4).

Continuously monitors discovered traders for new positions,
calls, and market commentary. Extracts trading signals.

__capability_tier__ = 0
__forbidden_tiers__ = (5,)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__capability_tier__ = 0
__forbidden_tiers__ = (5,)


class SignalType(StrEnum):
    """Types of signals extracted from trader content."""

    POSITION_OPEN = "position_open"
    POSITION_CLOSE = "position_close"
    PRICE_TARGET = "price_target"
    STOP_LOSS = "stop_loss"
    MARKET_VIEW = "market_view"
    REGIME_CALL = "regime_call"
    RISK_WARNING = "risk_warning"
    NARRATIVE_SHIFT = "narrative_shift"


@dataclass(frozen=True, slots=True)
class ExtractedSignal:
    """A signal extracted from trader content."""

    trader_id: str
    signal_type: SignalType
    symbol: str
    side: str  # "long" | "short" | "neutral"
    confidence: float
    price_level: float | None
    timeframe: str  # "scalp" | "intraday" | "swing" | "position"
    source_url: str
    raw_text: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class MonitoringSchedule:
    """Monitoring schedule for a trader."""

    trader_id: str
    check_interval_ns: int  # how often to check
    last_check_ts_ns: int
    priority: int  # 1=highest, 5=lowest
    active: bool


class TraderMonitor:
    """Monitors discovered traders and extracts signals.

    Periodically checks trader pages/feeds for new content,
    parses it for trading signals, and forwards to the
    trader_modeling pipeline.
    """

    def __init__(self, *, max_concurrent: int = 10) -> None:
        self._max_concurrent = max_concurrent
        self._schedules: dict[str, MonitoringSchedule] = {}
        self._signals: list[ExtractedSignal] = []
        self._signal_buffer_max = 1000

    def add_schedule(self, schedule: MonitoringSchedule) -> None:
        """Add or update a monitoring schedule."""
        self._schedules[schedule.trader_id] = schedule

    def remove_schedule(self, trader_id: str) -> None:
        """Remove a trader from monitoring."""
        self._schedules.pop(trader_id, None)

    def get_due_checks(self, *, current_ts_ns: int) -> list[str]:
        """Get trader IDs due for a monitoring check."""
        due: list[str] = []
        for schedule in self._schedules.values():
            if not schedule.active:
                continue
            if current_ts_ns - schedule.last_check_ts_ns >= schedule.check_interval_ns:
                due.append(schedule.trader_id)
        # Sort by priority
        due.sort(key=lambda tid: self._schedules[tid].priority)
        return due[: self._max_concurrent]

    def ingest_signal(self, signal: ExtractedSignal) -> None:
        """Add an extracted signal to the buffer."""
        self._signals.append(signal)
        if len(self._signals) > self._signal_buffer_max:
            self._signals = self._signals[-self._signal_buffer_max :]

    def get_signals(
        self,
        *,
        trader_id: str = "",
        signal_type: SignalType | None = None,
        since_ts_ns: int = 0,
        limit: int = 50,
    ) -> list[ExtractedSignal]:
        """Query extracted signals."""
        results = self._signals
        if trader_id:
            results = [s for s in results if s.trader_id == trader_id]
        if signal_type is not None:
            results = [s for s in results if s.signal_type == signal_type]
        if since_ts_ns:
            results = [s for s in results if s.ts_ns >= since_ts_ns]
        return results[-limit:]

    @property
    def active_schedules(self) -> int:
        """Count of active monitoring schedules."""
        return sum(1 for s in self._schedules.values() if s.active)

    @property
    def total_signals(self) -> int:
        """Total signals collected."""
        return len(self._signals)
