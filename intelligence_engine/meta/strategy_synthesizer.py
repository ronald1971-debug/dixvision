"""
intelligence_engine/meta/strategy_synthesizer.py
DIX VISION v42.2 — Strategy Synthesizer (meta layer)

Synthesizes new strategy parameter sets from archetype templates and
historical performance data. Child strategies are created by blending
archetype defaults with performance-weighted parameter adjustments.

All proposed parameter mutations are emitted as LearningUpdate records
for governance approval before deployment (INV-12).
"""

from __future__ import annotations

import hashlib
import threading
import time as _time
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.contracts.learning import LearningUpdate


@dataclass(frozen=True, slots=True)
class SynthesisRequest:
    """Request to synthesize a new strategy from an archetype."""
    archetype_id: str
    base_params: dict[str, float]
    performance_history: tuple[float, ...]  # recent P&L samples
    ts_ns: int


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    """Result of a strategy synthesis operation."""
    strategy_id: str
    archetype_id: str
    params: dict[str, float]
    expected_sharpe: float
    lineage_id: str     # parent archetype_id used as lineage anchor
    ts_ns: int


class StrategySynthesizer:
    """
    Creates new strategies by blending archetype templates with
    performance-driven adjustments.

    Thread-safe. All mutations require governance approval via
    LearningUpdate records.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._synthesis_count = 0

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        """
        Synthesize a new strategy from an archetype + performance data.

        The adjustment factor is derived from the mean recent P&L:
          - Positive mean → slight expansion of parameter values (+5%)
          - Negative mean → contraction (-5%)
          - Neutral → no adjustment
        """
        ts_ns = request.ts_ns or _time.time_ns()
        history = request.performance_history
        mean_pnl = sum(history) / len(history) if history else 0.0

        adj = 0.0
        if mean_pnl > 0:
            adj = 0.05
        elif mean_pnl < 0:
            adj = -0.05

        new_params = {
            k: v * (1.0 + adj)
            for k, v in request.base_params.items()
        }

        # Estimate Sharpe from performance history (simple proxy)
        expected_sharpe = _estimate_sharpe(history)

        strategy_id = f"{request.archetype_id}-synth-{uuid.uuid4().hex[:8]}"

        with self._lock:
            self._synthesis_count += 1

        return SynthesisResult(
            strategy_id=strategy_id,
            archetype_id=request.archetype_id,
            params=new_params,
            expected_sharpe=expected_sharpe,
            lineage_id=request.archetype_id,
            ts_ns=ts_ns,
        )

    def build_learning_updates(
        self,
        result: SynthesisResult,
        old_params: dict[str, float],
    ) -> list[LearningUpdate]:
        """
        Wrap parameter changes into LearningUpdate governance proposals.
        """
        updates: list[LearningUpdate] = []
        for param, new_val in result.params.items():
            old_val = old_params.get(param, 0.0)
            if abs(new_val - old_val) < 1e-12:
                continue
            updates.append(
                LearningUpdate(
                    ts_ns=result.ts_ns,
                    strategy_id=result.strategy_id,
                    parameter=param,
                    old_value=f"{old_val:.10f}",
                    new_value=f"{new_val:.10f}",
                    reason=f"synthesis from archetype={result.archetype_id}",
                    meta={
                        "lineage_id": result.lineage_id,
                        "expected_sharpe": f"{result.expected_sharpe:.6f}",
                    },
                )
            )
        return updates

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"synthesis_count": self._synthesis_count}


def _estimate_sharpe(history: tuple[float, ...]) -> float:
    """Simple Sharpe proxy: mean / std of P&L series."""
    import math
    n = len(history)
    if n < 2:
        return 0.0
    mean = sum(history) / n
    var = sum((x - mean) ** 2 for x in history) / n
    std = math.sqrt(var)
    if std < 1e-12:
        return 0.0
    return mean / std


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: StrategySynthesizer | None = None
_lock = threading.Lock()


def get_strategy_synthesizer() -> StrategySynthesizer:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = StrategySynthesizer()
    return _instance


__all__ = [
    "SynthesisRequest",
    "SynthesisResult",
    "StrategySynthesizer",
    "get_strategy_synthesizer",
]
