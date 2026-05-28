"""
financial_governance/leverage_monitor.py
DIX VISION v42.2 — Leverage Monitor

Leverage bounds must never be exceeded. High leverage amplifies losses
and accelerates liquidation. This monitor tracks per-(symbol, venue)
leverage and blocks further position increases when limits are hit.

Leverage = notional_value / margin_used.
"""

from __future__ import annotations

import threading
import time as _time
from collections import deque
from typing import Any

from core.contracts.financial_governance import (
    FinancialSeverity,
    LeverageBreach,
)
from state.ledger.event_store import append_event


_MAX_HISTORY = 500
_WARN_RATIO = 0.80  # warn at 80% of max leverage
_HIGH_RATIO = 0.95  # high severity at 95%


class LeverageMonitor:
    """
    Tracks leverage per (symbol, venue) pair.

    Thread-safe. Callers update leverage via update_leverage() and the
    monitor checks it against configured limits.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (symbol, venue) → max_leverage
        self._limits: dict[tuple[str, str], float] = {}
        # (symbol, venue) → current_leverage
        self._current: dict[tuple[str, str], float] = {}
        self._violations: deque[LeverageBreach] = deque(maxlen=_MAX_HISTORY)
        self._violation_count: int = 0

    # ------------------------------------------------------------------
    # Limit management
    # ------------------------------------------------------------------

    def set_limit(self, symbol: str, venue: str, max_leverage: float) -> None:
        """Set the maximum leverage limit for a (symbol, venue) pair."""
        with self._lock:
            self._limits[(symbol, venue)] = max_leverage

    # ------------------------------------------------------------------
    # Leverage updates
    # ------------------------------------------------------------------

    def update_leverage(
        self,
        symbol: str,
        venue: str,
        current_leverage: float,
    ) -> LeverageBreach | None:
        """
        Update leverage for a position and check against limits.

        Returns a LeverageBreach if the limit is approached or exceeded, else None.
        """
        with self._lock:
            self._current[(symbol, venue)] = current_leverage
            max_lev = self._limits.get((symbol, venue), 0.0)

        if max_lev <= 0:
            return None

        ratio = current_leverage / max_lev
        if ratio < _WARN_RATIO:
            return None

        ts_ns = _time.time_ns()
        if ratio >= 1.0:
            severity = FinancialSeverity.CRITICAL
        elif ratio >= _HIGH_RATIO:
            severity = FinancialSeverity.HIGH
        else:
            severity = FinancialSeverity.WARNING

        breach = LeverageBreach(
            ts_ns=ts_ns,
            symbol=symbol,
            venue=venue,
            current_leverage=current_leverage,
            max_leverage=max_lev,
            severity=severity,
            detail=f"leverage_ratio={ratio:.3f}",
        )

        if severity in (FinancialSeverity.CRITICAL, FinancialSeverity.HIGH):
            with self._lock:
                self._violations.append(breach)
                self._violation_count += 1

            append_event(
                "GOVERNANCE",
                "FINGOV_LEVERAGE_EXCEEDED",
                "financial_governance.leverage_monitor",
                {
                    "symbol": symbol,
                    "venue": venue,
                    "current_leverage": current_leverage,
                    "max_leverage": max_lev,
                    "severity": severity.value,
                    "detail": breach.detail,
                },
            )

        return breach

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def violation_count(self) -> int:
        with self._lock:
            return self._violation_count

    def recent_violations(self, n: int = 20) -> list[LeverageBreach]:
        with self._lock:
            items = list(self._violations)
        return items[-n:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "tracked_positions": len(self._current),
                "configured_limits": len(self._limits),
                "violation_count": self._violation_count,
            }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: LeverageMonitor | None = None
_lock = threading.Lock()


def get_leverage_monitor() -> LeverageMonitor:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = LeverageMonitor()
    return _instance


__all__ = ["LeverageMonitor", "get_leverage_monitor"]
