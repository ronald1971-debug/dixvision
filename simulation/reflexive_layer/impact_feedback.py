"""REFL-01 impact_feedback — own-order price impact feedback loop.

Tracks the accumulated price impact of our order flow on a per-symbol basis
and models exponential decay over time.  The market reacts adversely to large
or repeated orders; this module captures that effect as a stateful accumulator
exposed to the simulation tier.

Design
------
* ``apply_order`` adds impact proportional to ``qty * market_impact_bps``.
* ``decay`` reduces accumulated impact using continuous exponential decay:
  ``impact_t = impact_0 * 2^(-(Δt / decay_half_life_ns))``.
* All timestamps are caller-supplied (INV-15 — no wall-clock reads).
* Thread-safe via :class:`threading.Lock`; each public method acquires the
  lock for the duration of its mutation.

Authority constraints
---------------------
* OFFLINE tier — no imports from intelligence_engine, execution_engine,
  governance_engine, evolution_engine, or learning_engine.
* B27/B28/INV-71 — does NOT construct SignalEvent, ExecutionEvent,
  HazardEvent, or PatchProposal.
* INV-15 — no wall-clock reads; ts_ns supplied by caller in every method.
"""

from __future__ import annotations

import dataclasses
import math
import threading


__all__ = [
    "ImpactParams",
    "ImpactState",
    "ImpactFeedback",
]


@dataclasses.dataclass(frozen=True, slots=True)
class ImpactParams:
    """Configuration for the impact-feedback accumulator.

    Attributes:
        market_impact_bps: Basis points of impact added per unit of quantity.
            E.g. 1.0 means each unit of qty adds 1 bps of impact.
            Must be > 0.
        decay_half_life_ns: Nanoseconds over which accumulated impact halves.
            Must be > 0.
    """

    market_impact_bps: float
    decay_half_life_ns: int

    def __post_init__(self) -> None:
        if not self.market_impact_bps > 0.0:
            raise ValueError(
                f"ImpactParams.market_impact_bps must be > 0, got {self.market_impact_bps!r}"
            )
        if self.decay_half_life_ns <= 0:
            raise ValueError(
                f"ImpactParams.decay_half_life_ns must be > 0, got {self.decay_half_life_ns!r}"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class ImpactState:
    """Snapshot of accumulated impact for one symbol.

    Attributes:
        ts_ns: Timestamp of the last update (caller-supplied).
        symbol: Instrument identifier.
        accumulated_impact_bps: Current accumulated impact in basis points.
            Always >= 0.
    """

    ts_ns: int
    symbol: str
    accumulated_impact_bps: float


# Internal mutable record — never escapes the class.
@dataclasses.dataclass(slots=True)
class _SymbolRecord:
    ts_ns: int
    accumulated_impact_bps: float


class ImpactFeedback:
    """REFL-01 own-order impact feedback accumulator.

    Holds per-symbol :class:`_SymbolRecord` state.  All mutations are
    protected by a :class:`threading.Lock` so the class is safe to use
    from multiple simulation threads (e.g. parallel scenario runners).

    Usage::

        params = ImpactParams(market_impact_bps=2.0, decay_half_life_ns=60_000_000_000)
        fb = ImpactFeedback(params=params)
        state = fb.apply_order("BTC-USD", qty=10.0, ts_ns=1_000_000_000)
        state = fb.decay("BTC-USD", ts_ns=2_000_000_000)
        bps = fb.current_impact("BTC-USD")
    """

    __slots__ = ("_params", "_state", "_lock")

    def __init__(self, params: ImpactParams) -> None:
        if not isinstance(params, ImpactParams):
            raise TypeError(
                f"ImpactFeedback.params must be ImpactParams, got {type(params).__name__}"
            )
        self._params: ImpactParams = params
        self._state: dict[str, _SymbolRecord] = {}
        self._lock: threading.Lock = threading.Lock()

    @property
    def params(self) -> ImpactParams:
        return self._params

    def _get_or_create(self, symbol: str, ts_ns: int) -> _SymbolRecord:
        """Return existing record or create a zeroed one.  Must be called under lock."""
        if symbol not in self._state:
            self._state[symbol] = _SymbolRecord(ts_ns=ts_ns, accumulated_impact_bps=0.0)
        return self._state[symbol]

    def _apply_exponential_decay(self, record: _SymbolRecord, ts_ns: int) -> None:
        """Decay ``record`` in-place up to ``ts_ns``.  Must be called under lock."""
        delta_ns = ts_ns - record.ts_ns
        if delta_ns <= 0:
            return
        # Continuous exponential decay: impact *= 2^(-delta / half_life).
        exponent = -delta_ns / self._params.decay_half_life_ns
        decay_factor = math.pow(2.0, exponent)
        record.accumulated_impact_bps = max(0.0, record.accumulated_impact_bps * decay_factor)
        record.ts_ns = ts_ns

    def apply_order(self, symbol: str, qty: float, ts_ns: int) -> ImpactState:
        """Add market impact for an order of ``qty`` units at ``ts_ns``.

        Impact added = ``qty * params.market_impact_bps``.  Any elapsed time
        since the last update causes the existing impact to decay first before
        the new impact is added.

        Args:
            symbol: Instrument identifier (non-empty).
            qty: Order quantity (>= 0; negative quantities are treated as 0).
            ts_ns: Caller-supplied timestamp in nanoseconds (>= 0).

        Returns:
            Frozen :class:`ImpactState` after the update.
        """
        if not symbol:
            raise ValueError("ImpactFeedback.apply_order: symbol must be non-empty")
        if ts_ns < 0:
            raise ValueError(f"ImpactFeedback.apply_order: ts_ns must be >= 0, got {ts_ns!r}")
        qty = max(0.0, qty)
        added_bps = qty * self._params.market_impact_bps
        with self._lock:
            record = self._get_or_create(symbol, ts_ns)
            self._apply_exponential_decay(record, ts_ns)
            record.accumulated_impact_bps = max(0.0, record.accumulated_impact_bps + added_bps)
            record.ts_ns = ts_ns
            return ImpactState(
                ts_ns=record.ts_ns,
                symbol=symbol,
                accumulated_impact_bps=record.accumulated_impact_bps,
            )

    def decay(self, symbol: str, ts_ns: int) -> ImpactState:
        """Apply exponential decay to the accumulated impact for ``symbol``.

        If the symbol has no recorded state, returns a zeroed
        :class:`ImpactState` at ``ts_ns``.

        Args:
            symbol: Instrument identifier (non-empty).
            ts_ns: Caller-supplied timestamp in nanoseconds (>= 0).

        Returns:
            Frozen :class:`ImpactState` after decay.
        """
        if not symbol:
            raise ValueError("ImpactFeedback.decay: symbol must be non-empty")
        if ts_ns < 0:
            raise ValueError(f"ImpactFeedback.decay: ts_ns must be >= 0, got {ts_ns!r}")
        with self._lock:
            record = self._get_or_create(symbol, ts_ns)
            self._apply_exponential_decay(record, ts_ns)
            record.ts_ns = ts_ns
            return ImpactState(
                ts_ns=record.ts_ns,
                symbol=symbol,
                accumulated_impact_bps=record.accumulated_impact_bps,
            )

    def current_impact(self, symbol: str) -> float:
        """Return the current accumulated impact in bps for ``symbol``.

        Returns 0.0 if the symbol has never been seen.  Does NOT apply any
        decay — use :meth:`decay` first if you need the decayed value.

        Args:
            symbol: Instrument identifier.

        Returns:
            Current ``accumulated_impact_bps`` (>= 0).
        """
        with self._lock:
            record = self._state.get(symbol)
            if record is None:
                return 0.0
            return record.accumulated_impact_bps
