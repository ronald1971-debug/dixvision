"""core/coherence/mode_engine.py
DIX VISION v42.2 — System operating mode finite-state machine (FSM).

The :class:`ModeEngine` is the single source of truth for the system's
current operating mode. It enforces the legal transition table
(:data:`LEGAL_MODE_TRANSITIONS`) so that no caller can accidentally
skip phases or re-enter LIVE without an explicit operator-authorised
reset through BOOTSTRAP.

Key invariants:
* ``LIVE`` can only transition to ``HALTED``. A halted system cannot
  silently resume — it must go back through ``BOOTSTRAP`` (full reset).
* ``HALTED`` can only transition to ``BOOTSTRAP``, enforcing the full
  restart protocol and preventing silent unhalts.
* All mode transitions are recorded as :class:`ModeTransition` value
  objects so the coherence coordinator can surface them to governance.

Authority constraints:
* No imports from any ``*_engine`` package.
* No imports from ``state.ledger`` writers.
* All frozen dataclasses follow the ``@dataclass(frozen=True, slots=True)``
  pattern (INV-08, INV-15).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import StrEnum


class SystemMode(StrEnum):
    """System operating modes (FSM states).

    BOOTSTRAP  — system is initialising; no market interaction.
    LEARNING   — passive observation; no trade execution.
    OBSERVING  — active monitoring; paper signals may be generated.
    SHADOW     — shadow execution (paper fills alongside live market;
                 execution engine is dry-run only).
    LIVE       — full live execution is permitted.
    HALTED     — system is stopped; only BOOTSTRAP transition is legal.
    """

    BOOTSTRAP = "BOOTSTRAP"
    LEARNING = "LEARNING"
    OBSERVING = "OBSERVING"
    SHADOW = "SHADOW"
    LIVE = "LIVE"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class ModeTransition:
    """Immutable record of a single FSM mode change.

    Fields:
        ts_ns: Nanosecond timestamp of the transition (caller-supplied;
            not read from a clock so the module stays pure — INV-15).
        from_mode: Mode before the transition.
        to_mode: Mode after the transition.
        reason: Human-readable explanation required by the authoriser.
        authorised_by: Identity of the authority that approved the
            transition (e.g. ``"operator:alice"`` or
            ``"governance_engine"``).
    """

    ts_ns: int
    from_mode: SystemMode
    to_mode: SystemMode
    reason: str
    authorised_by: str


# ---------------------------------------------------------------------------
# Legal FSM transition table
# ---------------------------------------------------------------------------

#: The allowed transitions between system modes.
#:
#: Reading the dict as ``LEGAL_MODE_TRANSITIONS[current]`` gives the
#: set of modes the system is permitted to transition *to* from
#: ``current``. Any transition not listed here is illegal and
#: :meth:`ModeEngine.transition` will raise :exc:`ValueError`.
#:
#: Design decisions:
#: * From BOOTSTRAP the system can only move to LEARNING (first step
#:   of the cognitive build-out) or HALTED (abort on axiom failure).
#: * LEARNING → OBSERVING is the natural progression once basic
#:   models are warm. Stepping back to BOOTSTRAP resets learning.
#: * OBSERVING → SHADOW is the step that introduces paper execution.
#:   Stepping back to LEARNING is allowed (e.g. regime shift).
#: * SHADOW → LIVE requires explicit promotion. SHADOW → OBSERVING
#:   is allowed as a safe step-back.
#: * LIVE → HALTED only. No silent step-downs.
#: * HALTED → BOOTSTRAP only. Full reset protocol.
LEGAL_MODE_TRANSITIONS: dict[SystemMode, frozenset[SystemMode]] = {
    SystemMode.BOOTSTRAP: frozenset({SystemMode.LEARNING, SystemMode.HALTED}),
    SystemMode.LEARNING: frozenset({SystemMode.OBSERVING, SystemMode.BOOTSTRAP, SystemMode.HALTED}),
    SystemMode.OBSERVING: frozenset({SystemMode.SHADOW, SystemMode.LEARNING, SystemMode.HALTED}),
    SystemMode.SHADOW: frozenset({SystemMode.LIVE, SystemMode.OBSERVING, SystemMode.HALTED}),
    SystemMode.LIVE: frozenset({SystemMode.HALTED}),
    SystemMode.HALTED: frozenset({SystemMode.BOOTSTRAP}),
}


class ModeEngine:
    """Finite-state machine that guards all system mode transitions.

    Thread-safe via an internal :class:`threading.Lock`. All state
    reads are non-blocking; the lock is only held during transitions.

    Usage::

        engine = ModeEngine()
        t = engine.transition(
            SystemMode.LEARNING,
            reason="axioms verified, starting learning phase",
            authorised_by="operator:alice",
            ts_ns=time_source.now_ns(),
        )
    """

    def __init__(
        self,
        *,
        initial_mode: SystemMode = SystemMode.BOOTSTRAP,
    ) -> None:
        self._mode: SystemMode = initial_mode
        self._history: list[ModeTransition] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_mode(self) -> SystemMode:
        """The current operating mode (non-blocking read)."""
        return self._mode

    @property
    def history(self) -> tuple[ModeTransition, ...]:
        """Immutable snapshot of all recorded mode transitions."""
        with self._lock:
            return tuple(self._history)

    # ------------------------------------------------------------------
    # Transition
    # ------------------------------------------------------------------

    def transition(
        self,
        new_mode: SystemMode,
        *,
        reason: str,
        authorised_by: str,
        ts_ns: int,
    ) -> ModeTransition:
        """Attempt a transition from the current mode to ``new_mode``.

        Args:
            new_mode: The mode to transition to.
            reason: Mandatory human-readable justification.
            authorised_by: Identity of the authority approving the change.
            ts_ns: Timestamp of the transition (nanoseconds; caller
                provides this so the engine stays clock-free — INV-15).

        Returns:
            The :class:`ModeTransition` record for this change.

        Raises:
            ValueError: If the transition is not legal per
                :data:`LEGAL_MODE_TRANSITIONS`, or if ``reason`` or
                ``authorised_by`` are empty.
        """
        if not reason:
            raise ValueError("ModeEngine.transition: reason must be non-empty")
        if not authorised_by:
            raise ValueError("ModeEngine.transition: authorised_by must be non-empty")

        with self._lock:
            from_mode = self._mode
            allowed = LEGAL_MODE_TRANSITIONS.get(from_mode, frozenset())
            if new_mode not in allowed:
                raise ValueError(
                    f"ModeEngine: illegal transition {from_mode!r} → {new_mode!r}; "
                    f"allowed from {from_mode!r}: {sorted(str(m) for m in allowed)}"
                )
            record = ModeTransition(
                ts_ns=ts_ns,
                from_mode=from_mode,
                to_mode=new_mode,
                reason=reason,
                authorised_by=authorised_by,
            )
            self._mode = new_mode
            self._history.append(record)
            return record

    def is_live(self) -> bool:
        """True if the current mode is :attr:`SystemMode.LIVE`."""
        return self._mode is SystemMode.LIVE

    def is_halted(self) -> bool:
        """True if the current mode is :attr:`SystemMode.HALTED`."""
        return self._mode is SystemMode.HALTED

    def can_transition_to(self, mode: SystemMode) -> bool:
        """Return True if a transition to ``mode`` is currently legal."""
        return mode in LEGAL_MODE_TRANSITIONS.get(self._mode, frozenset())

    def __repr__(self) -> str:
        return f"ModeEngine(current_mode={self._mode!r}, transitions={len(self._history)})"


__all__ = [
    "LEGAL_MODE_TRANSITIONS",
    "ModeEngine",
    "ModeTransition",
    "SystemMode",
]
