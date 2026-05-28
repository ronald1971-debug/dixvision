"""core/coherence/meta_adaptation.py
DIX VISION v42.2 — Meta-adaptation coordinator.

Coordinates adaptation of system behaviour in response to drift signals
emitted by :class:`~core.coherence.drift_oracle.DriftOracle`. When a
:class:`~core.coherence.drift_oracle.DriftMeasure` crosses the warning
or critical threshold this module generates an
:class:`AdaptationSignal` that the coherence coordinator can surface
to the governance layer.

Design:
* Adaptation signals are *suggestions*, not commands. They require
  explicit approval via :meth:`MetaAdaptation.approve` before any
  downstream actor may act on them.
* Signals are keyed by a stable ``signal_id`` (
  ``f"{kind.value}:{metric_name}:{ts_ns}"``); approval is
  idempotent — approving an already-approved signal is a no-op that
  returns ``False``.
* The ``pending_signals`` list is drained by the coordinator on each
  coherence check. Approved signals remain in the history but are no
  longer returned by :meth:`pending_signals`.

Authority constraints:
* No imports from any ``*_engine`` package.
* No imports from ``state.ledger`` writers.
* :mod:`core.coherence.drift_oracle` is the only intra-package import.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.coherence.drift_oracle import DriftMeasure, DriftOracleConfig


class AdaptationKind(StrEnum):
    """Category of adaptation suggested by the meta-adaptation layer.

    PARAMETER_ADJUST      — adjust a model hyper-parameter (e.g. raise
                            a threshold in response to persistent delta).
    REGIME_RELABEL        — re-classify the current market regime.
    LEARNING_PAUSE        — suspend online learning while drift is active
                            to avoid reinforcing a bad distribution.
    MODE_TRANSITION_REQUEST — request the ModeEngine to step back one
                            level (e.g. LIVE → HALTED on critical drift).
    """

    PARAMETER_ADJUST = "PARAMETER_ADJUST"
    REGIME_RELABEL = "REGIME_RELABEL"
    LEARNING_PAUSE = "LEARNING_PAUSE"
    MODE_TRANSITION_REQUEST = "MODE_TRANSITION_REQUEST"


@dataclass(frozen=True, slots=True)
class AdaptationSignal:
    """Immutable suggestion for a system adaptation.

    Fields:
        ts_ns: Timestamp of the underlying drift sample (nanoseconds).
        kind: Category of adaptation suggested.
        metric_name: The metric that triggered this signal.
        z_score: The z-score at the time the signal was generated.
        suggested_action: Human-readable description of what should be
            done (e.g. ``"raise confidence threshold for EURUSD"``).
        approved: Whether this signal has been approved by a governance
            authority. Starts ``False``; set to ``True`` only via
            :meth:`MetaAdaptation.approve`.
    """

    ts_ns: int
    kind: AdaptationKind
    metric_name: str
    z_score: float
    suggested_action: str
    approved: bool = False


def _make_signal_id(kind: AdaptationKind, metric_name: str, ts_ns: int) -> str:
    """Return a stable string identifier for an adaptation signal."""
    return f"{kind.value}:{metric_name}:{ts_ns}"


class MetaAdaptation:
    """Generates and tracks adaptation signals driven by drift measures.

    Integrates with :class:`~core.coherence.drift_oracle.DriftOracle`:
    callers feed :class:`~core.coherence.drift_oracle.DriftMeasure`
    objects into :meth:`evaluate_drift`; this method decides whether to
    create an :class:`AdaptationSignal` (or ``None`` if the drift is
    below the warning threshold).

    Thread-safety: not thread-safe — serialize access at the coordinator
    level.
    """

    def __init__(
        self,
        *,
        oracle_config: DriftOracleConfig | None = None,
    ) -> None:
        self._config = oracle_config or DriftOracleConfig()
        # All signals ever generated, keyed by signal_id
        self._signals: dict[str, AdaptationSignal] = {}
        # Ordered list of signal_ids in creation order
        self._signal_order: list[str] = []

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate_drift(self, drift_measure: DriftMeasure) -> AdaptationSignal | None:
        """Evaluate a drift measure and optionally emit an adaptation signal.

        Decision logic:
        * ``|z_score| < z_warn``  → no signal (calibrated).
        * ``z_warn <= |z_score| < z_critical`` → PARAMETER_ADJUST or
          LEARNING_PAUSE depending on persistence.
        * ``|z_score| >= z_critical``  → MODE_TRANSITION_REQUEST
          (highest urgency).

        Args:
            drift_measure: A :class:`DriftMeasure` from the oracle.

        Returns:
            A new :class:`AdaptationSignal` if the z-score warrants
            action, or ``None`` if the system is within tolerance.
        """
        abs_z = abs(drift_measure.z_score)

        if abs_z < self._config.z_warn:
            return None

        if abs_z >= self._config.z_critical:
            kind = AdaptationKind.MODE_TRANSITION_REQUEST
            action = (
                f"Critical drift on {drift_measure.metric_name} "
                f"(z={drift_measure.z_score:.2f}): request mode step-down to HALTED"
            )
        elif drift_measure.drifting:
            # Persistent warning-level drift — pause learning to avoid
            # reinforcing the drifted distribution.
            kind = AdaptationKind.LEARNING_PAUSE
            action = (
                f"Warning drift on {drift_measure.metric_name} "
                f"(z={drift_measure.z_score:.2f}): pause online learning"
            )
        else:
            kind = AdaptationKind.PARAMETER_ADJUST
            action = (
                f"Soft drift on {drift_measure.metric_name} "
                f"(z={drift_measure.z_score:.2f}): consider parameter adjustment"
            )

        signal = AdaptationSignal(
            ts_ns=drift_measure.ts_ns,
            kind=kind,
            metric_name=drift_measure.metric_name,
            z_score=drift_measure.z_score,
            suggested_action=action,
            approved=False,
        )
        signal_id = _make_signal_id(kind, drift_measure.metric_name, drift_measure.ts_ns)
        if signal_id not in self._signals:
            self._signals[signal_id] = signal
            self._signal_order.append(signal_id)
        return signal

    # ------------------------------------------------------------------
    # Approval
    # ------------------------------------------------------------------

    def approve(self, signal_id: str) -> bool:
        """Approve a pending adaptation signal.

        Args:
            signal_id: The identifier string for the signal to approve.
                Obtain via :func:`_make_signal_id` or by calling
                :meth:`pending_signals` and constructing the id from the
                signal fields.

        Returns:
            ``True`` if the signal was found and its state changed from
            unapproved to approved. ``False`` if the signal was already
            approved or does not exist.
        """
        existing = self._signals.get(signal_id)
        if existing is None or existing.approved:
            return False
        # Replace with an approved copy (frozen dataclass)
        approved_signal = AdaptationSignal(
            ts_ns=existing.ts_ns,
            kind=existing.kind,
            metric_name=existing.metric_name,
            z_score=existing.z_score,
            suggested_action=existing.suggested_action,
            approved=True,
        )
        self._signals[signal_id] = approved_signal
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def pending_signals(self) -> tuple[AdaptationSignal, ...]:
        """Return all unapproved adaptation signals in creation order."""
        return tuple(
            self._signals[sid]
            for sid in self._signal_order
            if not self._signals[sid].approved
        )

    def all_signals(self) -> tuple[AdaptationSignal, ...]:
        """Return all signals (approved and pending) in creation order."""
        return tuple(self._signals[sid] for sid in self._signal_order)

    def signal_id_for(
        self,
        kind: AdaptationKind,
        metric_name: str,
        ts_ns: int,
    ) -> str:
        """Return the canonical signal_id for the given key triple."""
        return _make_signal_id(kind, metric_name, ts_ns)

    def __repr__(self) -> str:
        pending = sum(1 for s in self._signals.values() if not s.approved)
        return f"MetaAdaptation(total={len(self._signals)}, pending={pending})"


__all__ = [
    "AdaptationKind",
    "AdaptationSignal",
    "MetaAdaptation",
]
