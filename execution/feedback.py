"""execution.feedback — execution quality feedback collector.

Records post-trade execution quality signals (fill rate, slippage observed,
rejection reasons) so the learning engine and operator dashboard can query
aggregate execution health without touching the full TCA pipeline.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionFeedback:
    order_id: str
    symbol: str
    side: str
    requested_qty: float
    filled_qty: float
    avg_price: float
    slippage_bps: float
    venue: str
    outcome: str  # "filled" | "partial" | "rejected" | "cancelled"
    error: str = ""


class FeedbackCollector:
    """Thread-safe ring buffer of recent execution feedback entries."""

    _MAX_ENTRIES = 10_000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: deque[ExecutionFeedback] = deque(maxlen=self._MAX_ENTRIES)

    def record(self, feedback: ExecutionFeedback) -> None:
        with self._lock:
            self._entries.append(feedback)

    def recent(self, n: int = 100) -> list[ExecutionFeedback]:
        with self._lock:
            return list(self._entries)[-n:]

    def fill_rate(self) -> float:
        with self._lock:
            if not self._entries:
                return 1.0
            filled = sum(1 for e in self._entries if e.outcome == "filled")
            return filled / len(self._entries)

    def avg_slippage_bps(self) -> float:
        with self._lock:
            if not self._entries:
                return 0.0
            return sum(e.slippage_bps for e in self._entries) / len(self._entries)

    def snapshot(self) -> dict[str, Any]:
        return {
            "total_entries": len(self._entries),
            "fill_rate": round(self.fill_rate(), 4),
            "avg_slippage_bps": round(self.avg_slippage_bps(), 4),
        }


_collector: FeedbackCollector | None = None
_lock = threading.Lock()


def get_feedback_collector() -> FeedbackCollector:
    global _collector
    if _collector is None:
        with _lock:
            if _collector is None:
                _collector = FeedbackCollector()
    return _collector
