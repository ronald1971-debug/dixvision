"""core/coherence/engine.py
DIX VISION v42.2 — Central coordinator for the coherence subsystem.

The :class:`CoherenceEngine` is the single integration point that holds
lazy references to all coherence sub-components:

* :class:`~core.coherence.belief_state.BeliefState` derivation
* :class:`~core.coherence.performance_pressure.PressureVector` derivation
* :class:`~core.coherence.reflection_engine.ReflectionEngine`
* :class:`~core.coherence.system_intent.SystemIntent` derivation
* :class:`~core.coherence.mode_engine.ModeEngine`
* :class:`~core.coherence.drift_oracle.DriftOracle`
* :class:`~core.coherence.meta_adaptation.MetaAdaptation`

The coherence engine does NOT reach into any execution/intelligence/
learning engine — it is a pure projection and coordination layer that
other engines query read-only.

Singleton access is provided via :func:`get_coherence_engine` with
double-checked locking so the module is safe to import from multiple
threads during startup.

Authority constraints:
* No imports from any ``*_engine`` package.
* No imports from ``state.ledger`` writers.
* Only :mod:`core.coherence.*` and :mod:`core.contracts` are imported.
"""

from __future__ import annotations

import threading
from typing import Any

from core.coherence.drift_oracle import DriftOracle, DriftOracleConfig
from core.coherence.meta_adaptation import MetaAdaptation
from core.coherence.mode_engine import ModeEngine, SystemMode


class CoherenceEngine:
    """Central coordinator for all coherence projections.

    Holds lazy-initialised references to the coherence sub-components.
    Callers interact with it via:

    * :meth:`check_coherence` — returns a snapshot dict of the current
      state of every sub-component.
    * :attr:`current_mode` — delegates to the internal :class:`ModeEngine`.
    * Direct access to sub-components via guard properties (e.g.
      :attr:`mode_engine`, :attr:`drift_oracle`, :attr:`meta_adaptation`).

    Thread-safety: each sub-component is initialised lazily under an
    internal lock so concurrent first-accesses are safe.
    """

    def __init__(
        self,
        *,
        drift_oracle_config: DriftOracleConfig | None = None,
    ) -> None:
        self._lock = threading.Lock()

        # Core sub-components — initialised lazily
        self._mode_engine: ModeEngine | None = None
        self._drift_oracle: DriftOracle | None = None
        self._meta_adaptation: MetaAdaptation | None = None

        # Optional injected references (set by wiring layer)
        self._reflection_engine: Any = None
        self._belief_state: Any = None
        self._pressure_vector: Any = None
        self._system_intent: Any = None
        self._decision_trace: Any = None

        # Config for sub-components
        self._drift_oracle_config = drift_oracle_config or DriftOracleConfig()

    # ------------------------------------------------------------------
    # Lazy-guard properties for first-class sub-components
    # ------------------------------------------------------------------

    @property
    def mode_engine(self) -> ModeEngine:
        """Lazy-initialised :class:`ModeEngine` (thread-safe)."""
        if self._mode_engine is None:
            with self._lock:
                if self._mode_engine is None:
                    self._mode_engine = ModeEngine()
        return self._mode_engine

    @property
    def drift_oracle(self) -> DriftOracle:
        """Lazy-initialised :class:`DriftOracle` (thread-safe)."""
        if self._drift_oracle is None:
            with self._lock:
                if self._drift_oracle is None:
                    self._drift_oracle = DriftOracle(self._drift_oracle_config)
        return self._drift_oracle

    @property
    def meta_adaptation(self) -> MetaAdaptation:
        """Lazy-initialised :class:`MetaAdaptation` (thread-safe)."""
        if self._meta_adaptation is None:
            with self._lock:
                if self._meta_adaptation is None:
                    self._meta_adaptation = MetaAdaptation(
                        oracle_config=self._drift_oracle_config
                    )
        return self._meta_adaptation

    # ------------------------------------------------------------------
    # Injected optional references (set by the wiring layer at startup)
    # ------------------------------------------------------------------

    def set_reflection_engine(self, engine: Any) -> None:
        """Inject the reflection engine reference."""
        with self._lock:
            self._reflection_engine = engine

    def set_belief_state_ref(self, ref: Any) -> None:
        """Inject a callable that returns the current BeliefState snapshot."""
        with self._lock:
            self._belief_state = ref

    def set_pressure_vector_ref(self, ref: Any) -> None:
        """Inject a callable that returns the current PressureVector snapshot."""
        with self._lock:
            self._pressure_vector = ref

    def set_system_intent_ref(self, ref: Any) -> None:
        """Inject a callable that returns the current SystemIntent snapshot."""
        with self._lock:
            self._system_intent = ref

    def set_decision_trace_ref(self, ref: Any) -> None:
        """Inject a reference to the decision trace builder."""
        with self._lock:
            self._decision_trace = ref

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    @property
    def current_mode(self) -> SystemMode:
        """Delegate to the internal :class:`ModeEngine`."""
        return self.mode_engine.current_mode

    def check_coherence(self) -> dict[str, Any]:
        """Return a snapshot of the current coherence subsystem state.

        The snapshot is a plain dict so callers have no live reference
        into the engine's internals. Keys:

        * ``mode``:  Current :class:`~core.coherence.mode_engine.SystemMode`.
        * ``mode_transitions``: Number of recorded mode transitions.
        * ``drift_summary``: ``{metric_name: z_score}`` from the oracle.
        * ``pending_adaptations``: Count of unapproved adaptation signals.
        * ``reflection_count``: Number of completed reflections (if the
          reflection engine has been injected), else ``None``.
        * ``belief_drift_keys``: Sorted list of accumulated belief-drift
          keys (if the reflection engine has been injected), else ``None``.
        * ``components_present``: Dict of which optional components have
          been injected.
        """
        mode_eng = self.mode_engine
        oracle = self.drift_oracle
        meta = self.meta_adaptation

        reflection_count: int | None = None
        belief_drift_keys: list[str] | None = None
        if self._reflection_engine is not None:
            try:
                reflection_count = len(self._reflection_engine.reflections)
                belief_drift_keys = sorted(self._reflection_engine.belief_drift.keys())
            except Exception:
                pass

        return {
            "mode": mode_eng.current_mode.value,
            "mode_transitions": len(mode_eng.history),
            "drift_summary": oracle.get_drift_summary(),
            "pending_adaptations": len(meta.pending_signals()),
            "reflection_count": reflection_count,
            "belief_drift_keys": belief_drift_keys,
            "components_present": {
                "reflection_engine": self._reflection_engine is not None,
                "belief_state": self._belief_state is not None,
                "pressure_vector": self._pressure_vector is not None,
                "system_intent": self._system_intent is not None,
                "decision_trace": self._decision_trace is not None,
            },
        }

    def __repr__(self) -> str:
        mode = self._mode_engine.current_mode.value if self._mode_engine else "uninitialised"
        return f"CoherenceEngine(mode={mode!r})"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_engine_instance: CoherenceEngine | None = None
_engine_lock = threading.Lock()


def get_coherence_engine(
    *,
    drift_oracle_config: DriftOracleConfig | None = None,
) -> CoherenceEngine:
    """Return the process-level :class:`CoherenceEngine` singleton.

    Double-checked locking — safe for concurrent first-calls from
    multiple threads during startup.

    Args:
        drift_oracle_config: Optional config supplied only on the *first*
            call. Subsequent calls ignore this parameter; pass ``None``
            to use the current singleton.

    Returns:
        The singleton :class:`CoherenceEngine` instance.
    """
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = CoherenceEngine(
                    drift_oracle_config=drift_oracle_config,
                )
    return _engine_instance


def _reset_coherence_engine_for_tests() -> None:
    """Reset the singleton — for use in tests only.

    Never call this in production code. Guarded by a module-internal
    name so it is not accidentally imported via ``from core.coherence.engine
    import *``.
    """
    global _engine_instance
    with _engine_lock:
        _engine_instance = None


__all__ = [
    "CoherenceEngine",
    "get_coherence_engine",
]
