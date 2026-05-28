"""
financial_governance/capital_throttle.py
DIX VISION v42.2 — Capital Throttle

Limits the rate at which capital is deployed. A large burst of orders
in a short window can exceed risk budgets faster than the exposure guard
can react, especially during volatile markets.

The throttle uses a rolling window: capital deployed in the last
WINDOW_NS nanoseconds must not exceed LIMIT_USD. If the limit is hit,
new deployments are blocked until the window rolls forward.

This is a soft gate during development (no real capital). It becomes
a hard gate in live deployment.
"""

from __future__ import annotations

import threading
import time as _time
from collections import deque
from typing import Any

from core.contracts.financial_governance import CapitalThrottleStatus
from state.ledger.event_store import append_event


_MAX_HISTORY = 500
DEFAULT_WINDOW_NS = 60 * 1_000_000_000   # 1-minute rolling window
DEFAULT_LIMIT_USD = 100_000.0             # $100k per minute default cap


class CapitalThrottle:
    """
    Rolling-window capital deployment rate limiter.

    Thread-safe. Callers call record_deployment() when capital is deployed
    and check_throttle() to see whether new deployments are allowed.
    """

    def __init__(
        self,
        window_ns: int = DEFAULT_WINDOW_NS,
        limit_usd: float = DEFAULT_LIMIT_USD,
    ) -> None:
        self._lock = threading.Lock()
        self._window_ns = window_ns
        self._limit_usd = limit_usd
        # (ts_ns, amount_usd) pairs in rolling window
        self._deployments: deque[tuple[int, float]] = deque()
        self._status_history: deque[CapitalThrottleStatus] = deque(maxlen=_MAX_HISTORY)
        self._throttle_count: int = 0

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(self, window_ns: int, limit_usd: float) -> None:
        """Update throttle configuration (operator only)."""
        with self._lock:
            self._window_ns = window_ns
            self._limit_usd = limit_usd

    # ------------------------------------------------------------------
    # Deployment recording
    # ------------------------------------------------------------------

    def record_deployment(self, amount_usd: float) -> CapitalThrottleStatus:
        """
        Record a capital deployment event.

        Returns the current throttle status. If throttled=True, the
        caller must NOT proceed with the deployment.
        """
        ts_ns = _time.time_ns()
        with self._lock:
            self._deployments.append((ts_ns, amount_usd))
            self._trim_window(ts_ns)
            deployed = sum(a for _, a in self._deployments)
            utilisation = deployed / self._limit_usd if self._limit_usd > 0 else 0.0
            throttled = deployed > self._limit_usd
            if throttled:
                self._throttle_count += 1

            status = CapitalThrottleStatus(
                ts_ns=ts_ns,
                window_ns=self._window_ns,
                deployed_usd=deployed,
                limit_usd=self._limit_usd,
                utilisation=utilisation,
                throttled=throttled,
                detail=(
                    f"deployed=${deployed:.0f} / limit=${self._limit_usd:.0f}"
                ),
            )
            self._status_history.append(status)

        if throttled:
            append_event(
                "GOVERNANCE",
                "FINGOV_CAPITAL_RATE_EXCEEDED",
                "financial_governance.capital_throttle",
                {
                    "deployed_usd": deployed,
                    "limit_usd": self._limit_usd,
                    "window_ns": self._window_ns,
                    "utilisation": utilisation,
                },
            )

        return status

    def check_throttle(self) -> CapitalThrottleStatus:
        """Return the current throttle status without recording a deployment."""
        ts_ns = _time.time_ns()
        with self._lock:
            self._trim_window(ts_ns)
            deployed = sum(a for _, a in self._deployments)
            utilisation = deployed / self._limit_usd if self._limit_usd > 0 else 0.0
            throttled = deployed >= self._limit_usd

        return CapitalThrottleStatus(
            ts_ns=ts_ns,
            window_ns=self._window_ns,
            deployed_usd=deployed,
            limit_usd=self._limit_usd,
            utilisation=utilisation,
            throttled=throttled,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _trim_window(self, now_ns: int) -> None:
        """Remove deployments older than the rolling window. Caller holds _lock."""
        cutoff = now_ns - self._window_ns
        while self._deployments and self._deployments[0][0] < cutoff:
            self._deployments.popleft()

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def throttle_count(self) -> int:
        with self._lock:
            return self._throttle_count

    def snapshot(self) -> dict[str, Any]:
        status = self.check_throttle()
        return {
            "deployed_usd": status.deployed_usd,
            "limit_usd": status.limit_usd,
            "utilisation": status.utilisation,
            "throttled": status.throttled,
            "window_ns": self._window_ns,
            "throttle_count": self._throttle_count,
        }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: CapitalThrottle | None = None
_lock = threading.Lock()


def get_capital_throttle() -> CapitalThrottle:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = CapitalThrottle()
    return _instance


__all__ = ["CapitalThrottle", "get_capital_throttle"]
