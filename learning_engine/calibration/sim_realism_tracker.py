"""learning_engine/calibration/sim_realism_tracker.py
DIX VISION v42.2 — Simulation Realism Tracker

Tracks divergence between simulation outcomes and live execution results
to calibrate simulator fidelity. Compares key metrics (fill rate, slippage,
latency, PnL distributions) between SIM and LIVE episodes.

Thread-safe. Emits LearningUpdate governance proposals when calibration
drift exceeds thresholds (INV-12 / INV-53).

Pure stats accumulation — no IO in core logic (INV-15).
"""

from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any

from core.contracts.learning import LearningUpdate


@dataclass(frozen=True, slots=True)
class EpisodeOutcome:
    """Key metrics from one trading episode (SIM or LIVE)."""
    strategy_id: str
    mode: str              # SIM | LIVE
    total_pnl: float
    fill_rate: float       # fills / orders [0,1]
    mean_slippage_bps: float
    mean_latency_ms: float
    num_trades: int
    ts_ns: int


@dataclass(frozen=True, slots=True)
class RealismReport:
    """Divergence report between SIM and LIVE for one strategy."""
    strategy_id: str
    sample_count_sim: int
    sample_count_live: int
    pnl_divergence: float          # abs(mean_sim_pnl - mean_live_pnl) / max(|mean_live|, eps)
    slippage_divergence_bps: float
    latency_divergence_ms: float
    fill_rate_divergence: float
    realism_score: float           # 1 - composite_divergence, clamped [0,1]
    needs_calibration: bool
    ts_ns: int


_CALIBRATION_THRESHOLD = 0.20   # >20% divergence triggers calibration


class SimRealismTracker:
    """
    Tracks SIM vs LIVE outcome divergence for calibration.

    Thread-safe. Records EpisodeOutcome samples; generates RealismReport
    snapshots on demand and wraps calibration proposals as LearningUpdates.
    """

    def __init__(self, window: int = 100) -> None:
        self._window = window
        self._lock = threading.Lock()
        self._sim: dict[str, deque[EpisodeOutcome]] = {}
        self._live: dict[str, deque[EpisodeOutcome]] = {}

    def record(self, outcome: EpisodeOutcome) -> None:
        with self._lock:
            bucket = self._sim if outcome.mode.upper() == "SIM" else self._live
            if outcome.strategy_id not in bucket:
                bucket[outcome.strategy_id] = deque(maxlen=self._window)
            bucket[outcome.strategy_id].append(outcome)

    def report(self, strategy_id: str, ts_ns: int) -> RealismReport:
        with self._lock:
            sim_samples = list(self._sim.get(strategy_id, []))
            live_samples = list(self._live.get(strategy_id, []))

        def _mean(vals: list[float]) -> float:
            return sum(vals) / len(vals) if vals else 0.0

        if not sim_samples or not live_samples:
            return RealismReport(
                strategy_id=strategy_id,
                sample_count_sim=len(sim_samples),
                sample_count_live=len(live_samples),
                pnl_divergence=0.0,
                slippage_divergence_bps=0.0,
                latency_divergence_ms=0.0,
                fill_rate_divergence=0.0,
                realism_score=1.0,
                needs_calibration=False,
                ts_ns=ts_ns,
            )

        mean_sim_pnl = _mean([r.total_pnl for r in sim_samples])
        mean_live_pnl = _mean([r.total_pnl for r in live_samples])
        eps = 1e-8
        pnl_div = abs(mean_sim_pnl - mean_live_pnl) / max(abs(mean_live_pnl), eps)

        slip_sim = _mean([r.mean_slippage_bps for r in sim_samples])
        slip_live = _mean([r.mean_slippage_bps for r in live_samples])
        slip_div = abs(slip_sim - slip_live) / max(abs(slip_live), eps)

        lat_sim = _mean([r.mean_latency_ms for r in sim_samples])
        lat_live = _mean([r.mean_latency_ms for r in live_samples])
        lat_div = abs(lat_sim - lat_live) / max(abs(lat_live), eps)

        fill_sim = _mean([r.fill_rate for r in sim_samples])
        fill_live = _mean([r.fill_rate for r in live_samples])
        fill_div = abs(fill_sim - fill_live)

        composite = (pnl_div + slip_div * 0.5 + lat_div * 0.3 + fill_div) / 4
        realism_score = max(0.0, min(1.0, 1.0 - composite))
        needs_calibration = composite > _CALIBRATION_THRESHOLD

        return RealismReport(
            strategy_id=strategy_id,
            sample_count_sim=len(sim_samples),
            sample_count_live=len(live_samples),
            pnl_divergence=pnl_div,
            slippage_divergence_bps=slip_div,
            latency_divergence_ms=lat_div,
            fill_rate_divergence=fill_div,
            realism_score=realism_score,
            needs_calibration=needs_calibration,
            ts_ns=ts_ns,
        )

    def build_calibration_update(
        self,
        report: RealismReport,
    ) -> list[LearningUpdate]:
        if not report.needs_calibration:
            return []
        return [
            LearningUpdate(
                ts_ns=report.ts_ns,
                strategy_id=report.strategy_id,
                parameter="sim_realism_score",
                old_value="1.0",
                new_value=f"{report.realism_score:.6f}",
                reason="sim_realism_calibration_drift",
                meta={
                    "pnl_divergence": f"{report.pnl_divergence:.6f}",
                    "slippage_divergence_bps": f"{report.slippage_divergence_bps:.6f}",
                },
            )
        ]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "tracked_strategies": list(set(list(self._sim.keys()) + list(self._live.keys()))),
                "window": self._window,
            }


# Singleton factory
_instance: SimRealismTracker | None = None
_lock = threading.Lock()


def get_sim_realism_tracker() -> SimRealismTracker:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = SimRealismTracker()
    return _instance


__all__ = [
    "EpisodeOutcome",
    "RealismReport",
    "SimRealismTracker",
    "get_sim_realism_tracker",
]
