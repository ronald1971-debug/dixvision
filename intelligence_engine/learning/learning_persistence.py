"""LearningPersistence — durable parameter evolution for INDIRA (P0 Emergence).

Wraps SlowLoopLearner with SQLite persistence so INDIRA's learned parameters
survive process restarts.  Without this, every restart resets confidence_baseline
to 0.65 regardless of whether the system has spent hours learning that 0.72 is
the right value for the current market regime.

Tracked parameters:
    confidence_baseline     — ThoughtRuntime's base confidence when no market
                              override is present.  Range [0.40, 0.95].
    signal_window_target    — Target depth for the intelligence engine's signal
                              accumulation window.  Range [5, 50].
    regime_hysteresis       — Confidence delta required to trigger a regime flip.
                              Range [0.05, 0.40].
    strategy_blend_alpha    — EMA smoothing factor for strategy score blending.
                              Range [0.05, 0.50].

Usage:
    lp = get_learning_persistence()
    lp.submit_feedback("confidence_baseline", reward=0.8, ts_ns=ts_ns)
    snap = lp.tick(ts_ns=ts_ns)
    vals = lp.current_values()  # {"confidence_baseline": 0.71, ...}

Authority (B1): imports only from intelligence_engine.* and core.*.
INV-15: ts_ns is caller-supplied; no wall-clock reads.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from intelligence_engine.learning.slow_loop import (
    DEFAULT_EMA_ALPHA,
    FeedbackSample,
    ParameterBounds,
    ParameterSnapshot,
    SlowLoopLearner,
)

_logger = logging.getLogger(__name__)

_STORE_KIND = "learning_persistence"

# ---------------------------------------------------------------------------
# Parameter definitions
# ---------------------------------------------------------------------------

_PARAMETER_BOUNDS: dict[str, ParameterBounds] = {
    "confidence_baseline": ParameterBounds(lo=0.40, hi=0.95, step=0.02, initial=0.65),
    "signal_window_target": ParameterBounds(lo=5.0, hi=50.0, step=1.0, initial=20.0),
    "regime_hysteresis": ParameterBounds(lo=0.05, hi=0.40, step=0.01, initial=0.15),
    "strategy_blend_alpha": ParameterBounds(lo=0.05, hi=0.50, step=0.02, initial=0.20),
}


# ---------------------------------------------------------------------------
# LearningPersistence
# ---------------------------------------------------------------------------


class LearningPersistence:
    """SlowLoopLearner with SQLite-backed persistence.

    Gate 1 (LearningEvolutionFreezePolicy) is checked on every tick;
    when frozen the learner drains the buffer without applying updates
    — the parameter values stay at their last learned position.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tick_count = 0
        self._learner = SlowLoopLearner(
            _PARAMETER_BOUNDS,
            time_unix_s_provider=lambda: 0,   # INV-15: do not read wall clock
            freeze_policy=self._make_freeze_policy(),
            ema_alpha=DEFAULT_EMA_ALPHA,
        )
        self._last_snapshot: ParameterSnapshot | None = None
        self._restore()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit_feedback(
        self,
        parameter: str,
        reward: float,
        *,
        weight: float = 1.0,
        ts_ns: int,
    ) -> bool:
        """Buffer one feedback observation.

        Args:
            parameter: One of the tracked parameter names.
            reward: Signed reward signal — positive means "push parameter up".
            weight: Sample weight (default 1.0).
            ts_ns: Caller-supplied timestamp (INV-15).

        Returns:
            True if the sample was accepted; False if the parameter is unknown.
        """
        sample = FeedbackSample(
            ts_unix_s=ts_ns // 1_000_000_000,
            parameter=parameter,
            reward=reward,
            weight=weight,
        )
        with self._lock:
            return self._learner.submit(sample)

    def tick(self, *, ts_ns: int) -> ParameterSnapshot:
        """Drain buffered samples, update parameters, persist to SQLite.

        Returns the new ParameterSnapshot with updated values.
        """
        with self._lock:
            self._tick_count += 1
            snap = self._learner.tick()
            self._last_snapshot = snap
        self._persist(snap, ts_ns)
        return snap

    def current_values(self) -> dict[str, float]:
        """Return the current parameter values (post-last-tick)."""
        with self._lock:
            if self._last_snapshot is not None:
                return dict(self._last_snapshot.values)
            # Pre-tick: return initial values
            return {n: b.initial for n, b in _PARAMETER_BOUNDS.items()}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            vals = dict(self._last_snapshot.values) if self._last_snapshot else {}
            frozen = self._last_snapshot.frozen if self._last_snapshot else False
        return {
            "tick_count": self._tick_count,
            "frozen": frozen,
            "parameters": vals,
            "parameter_names": list(_PARAMETER_BOUNDS.keys()),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, snap: ParameterSnapshot, ts_ns: int) -> None:
        try:
            from state.cognition_persistence import get_cognition_persistence_store
            get_cognition_persistence_store().save_episode(
                store_kind=_STORE_KIND,
                episode_id=f"lp_snap_{self._tick_count}",
                ts_ns=ts_ns,
                data={
                    "values": dict(snap.values),
                    "ema": dict(snap.ema),
                    "sample_counts": dict(snap.sample_counts),
                    "frozen": snap.frozen,
                    "version": snap.version,
                    "tick_count": self._tick_count,
                },
            )
        except Exception as exc:
            _logger.debug("LearningPersistence._persist error: %s", exc)

    def _restore(self) -> None:
        """Load the most recent ParameterSnapshot from SQLite and seed the learner."""
        try:
            from state.cognition_persistence import get_cognition_persistence_store
            rows = get_cognition_persistence_store().load_episodes(_STORE_KIND, limit=1)
            if not rows:
                return
            d = rows[0]
            values: dict[str, float] = d.get("values", {})
            ema: dict[str, float] = d.get("ema", {})
            sample_counts: dict[str, int] = d.get("sample_counts", {})
            # Seed learner state by submitting one feedback sample per param
            # that nudges it toward the previously learned value.  The magnitude
            # is large enough to override the EMA warmup in one tick.
            for name, learned_val in values.items():
                st = self._learner._params.get(name)  # noqa: SLF001
                if st is None:
                    continue
                st.value = max(st.bounds.lo, min(st.bounds.hi, float(learned_val)))
                st.ema = float(ema.get(name, 0.0))
                st.samples_seen = int(sample_counts.get(name, 0))
            # Reconstruct a synthetic snapshot representing the restored state
            self._last_snapshot = ParameterSnapshot(
                ts_unix_s=0,
                version=str(d.get("version", "v1")),
                values={n: self._learner._params[n].value for n in _PARAMETER_BOUNDS},  # noqa: SLF001
                ema={n: self._learner._params[n].ema for n in _PARAMETER_BOUNDS},  # noqa: SLF001
                sample_counts={
                    n: self._learner._params[n].samples_seen for n in _PARAMETER_BOUNDS  # noqa: SLF001
                },
                frozen=False,
            )
            _logger.info(
                "LearningPersistence: restored parameters from persistence — "
                "confidence_baseline=%.3f",
                values.get("confidence_baseline", 0.65),
            )
        except Exception as exc:
            _logger.debug("LearningPersistence._restore error: %s", exc)

    # ------------------------------------------------------------------
    # Freeze policy
    # ------------------------------------------------------------------

    @staticmethod
    def _make_freeze_policy() -> Any:
        """Construct an always-open LearningEvolutionFreezePolicy (Gate 1)."""
        try:
            from core.contracts.learning_evolution_freeze import LearningEvolutionFreezePolicy
            from core.contracts.governance import SystemMode
            return LearningEvolutionFreezePolicy(mode=getattr(SystemMode, "PAPER"), operator_override=True)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_persistence: LearningPersistence | None = None
_persistence_lock = threading.Lock()


def get_learning_persistence() -> LearningPersistence:
    """Return the process-wide LearningPersistence singleton."""
    global _persistence
    with _persistence_lock:
        if _persistence is None:
            _persistence = LearningPersistence()
    return _persistence


__all__ = [
    "LearningPersistence",
    "get_learning_persistence",
]
