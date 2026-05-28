"""
financial_governance/liquidation_sentinel.py
DIX VISION v42.2 — Liquidation Sentinel

Early warning system for positions approaching liquidation price.
Liquidation wipes the position and costs extra fees. The sentinel
warns while there is still time to reduce exposure.

distance_pct = (mark_price - liquidation_price) / mark_price × 100

Warning tiers:
  distance_pct < WARNING_THRESHOLD  → WARNING
  distance_pct < HIGH_THRESHOLD     → HIGH
  distance_pct < CRITICAL_THRESHOLD → CRITICAL

For short positions the signs are reversed; callers must pass the
positive distance_pct regardless of direction.
"""

from __future__ import annotations

import threading
import time as _time
from collections import deque
from typing import Any

from core.contracts.financial_governance import (
    FinancialSeverity,
    LiquidationRiskRecord,
)
from state.ledger.event_store import append_event


_MAX_HISTORY = 500

WARNING_THRESHOLD_PCT  = 15.0
HIGH_THRESHOLD_PCT     = 7.5
CRITICAL_THRESHOLD_PCT = 3.0


class LiquidationSentinel:
    """
    Early warning monitor for liquidation proximity.

    Thread-safe. Callers update position state via update_position();
    the sentinel computes severity and emits warnings as needed.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: deque[LiquidationRiskRecord] = deque(maxlen=_MAX_HISTORY)
        self._violation_count: int = 0
        # position_id → last severity for de-duplication
        self._last_severity: dict[str, FinancialSeverity] = {}

    # ------------------------------------------------------------------
    # Position updates
    # ------------------------------------------------------------------

    def update_position(
        self,
        position_id: str,
        symbol: str,
        venue: str,
        mark_price: float,
        liquidation_price: float,
    ) -> LiquidationRiskRecord | None:
        """
        Update a position's mark and liquidation prices.

        Returns a LiquidationRiskRecord if within warning range, else None.
        Emits FINGOV_LIQUIDATION_IMMINENT when severity is HIGH or CRITICAL.
        """
        if liquidation_price <= 0 or mark_price <= 0:
            return None

        distance_pct = abs(mark_price - liquidation_price) / mark_price * 100.0

        if distance_pct >= WARNING_THRESHOLD_PCT:
            with self._lock:
                self._last_severity.pop(position_id, None)
            return None

        ts_ns = _time.time_ns()
        if distance_pct < CRITICAL_THRESHOLD_PCT:
            severity = FinancialSeverity.CRITICAL
        elif distance_pct < HIGH_THRESHOLD_PCT:
            severity = FinancialSeverity.HIGH
        else:
            severity = FinancialSeverity.WARNING

        record = LiquidationRiskRecord(
            ts_ns=ts_ns,
            position_id=position_id,
            symbol=symbol,
            venue=venue,
            mark_price=mark_price,
            liquidation_price=liquidation_price,
            distance_pct=distance_pct,
            warning_threshold_pct=WARNING_THRESHOLD_PCT,
            severity=severity,
            detail=f"distance={distance_pct:.2f}%",
        )

        with self._lock:
            last = self._last_severity.get(position_id)
            changed = last != severity
            self._last_severity[position_id] = severity
            self._records.append(record)
            if severity in (FinancialSeverity.CRITICAL, FinancialSeverity.HIGH):
                self._violation_count += 1

        if changed and severity in (FinancialSeverity.CRITICAL, FinancialSeverity.HIGH):
            append_event(
                "GOVERNANCE",
                "FINGOV_LIQUIDATION_IMMINENT",
                "financial_governance.liquidation_sentinel",
                {
                    "position_id": position_id,
                    "symbol": symbol,
                    "venue": venue,
                    "mark_price": mark_price,
                    "liquidation_price": liquidation_price,
                    "distance_pct": distance_pct,
                    "severity": severity.value,
                },
            )

        return record

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def at_risk_positions(self) -> dict[str, FinancialSeverity]:
        """Return position_id → severity for all currently-at-risk positions."""
        with self._lock:
            return dict(self._last_severity)

    def violation_count(self) -> int:
        with self._lock:
            return self._violation_count

    def recent_records(self, n: int = 20) -> list[LiquidationRiskRecord]:
        with self._lock:
            items = list(self._records)
        return items[-n:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "at_risk_count": len(self._last_severity),
                "critical_count": sum(
                    1 for s in self._last_severity.values()
                    if s is FinancialSeverity.CRITICAL
                ),
                "violation_count": self._violation_count,
            }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: LiquidationSentinel | None = None
_lock = threading.Lock()


def get_liquidation_sentinel() -> LiquidationSentinel:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = LiquidationSentinel()
    return _instance


__all__ = ["LiquidationSentinel", "get_liquidation_sentinel"]
