"""REFL-02 liquidity_decay — liquidity drying up under our flow.

Models the per-symbol available liquidity as a fraction of normal depth
in [0.0, 1.0].  As we consume liquidity (via ``consume``), the fraction
drops.  Over time, market-maker replenishment restores liquidity (via
``replenish``).

Design
------
* ``consume`` decreases available_liquidity by ``qty * decay_rate_per_unit``.
  Result is clamped to [0.0, 1.0].
* ``replenish`` increases available_liquidity by
  ``Δt_ns * replenish_rate_per_ns``.  Result is clamped to [0.0, 1.0].
* All timestamps are caller-supplied (INV-15 — no wall-clock reads).
* Pure state machine — no PRNG.

Authority constraints
---------------------
* OFFLINE tier — no imports from intelligence_engine, execution_engine,
  governance_engine, evolution_engine, or learning_engine.
* B27/B28/INV-71 — does NOT construct SignalEvent, ExecutionEvent,
  HazardEvent, or PatchProposal.
* INV-15 — no wall-clock reads; ts_ns supplied by caller.
"""

from __future__ import annotations

import dataclasses


__all__ = [
    "LiquidityDecayParams",
    "LiquidityState",
    "LiquidityDecay",
]


@dataclasses.dataclass(frozen=True, slots=True)
class LiquidityDecayParams:
    """Configuration for the liquidity-decay state machine.

    Attributes:
        decay_rate_per_unit: Fraction of available liquidity removed per unit
            of quantity consumed.  E.g. 0.01 means each unit of qty removes
            1% of available liquidity.  Must be in (0.0, 1.0].
        replenish_rate_per_ns: Fraction of normal liquidity restored per
            nanosecond of elapsed time.  Must be > 0.
    """

    decay_rate_per_unit: float
    replenish_rate_per_ns: float

    def __post_init__(self) -> None:
        if not 0.0 < self.decay_rate_per_unit <= 1.0:
            raise ValueError(
                "LiquidityDecayParams.decay_rate_per_unit must be in (0.0, 1.0], "
                f"got {self.decay_rate_per_unit!r}"
            )
        if not self.replenish_rate_per_ns > 0.0:
            raise ValueError(
                "LiquidityDecayParams.replenish_rate_per_ns must be > 0, "
                f"got {self.replenish_rate_per_ns!r}"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class LiquidityState:
    """Snapshot of available liquidity for one symbol.

    Attributes:
        ts_ns: Timestamp of the last update (caller-supplied).
        symbol: Instrument identifier.
        available_liquidity: Fraction of normal liquidity remaining.
            Always in [0.0, 1.0].  1.0 = fully replenished; 0.0 = dry.
    """

    ts_ns: int
    symbol: str
    available_liquidity: float


# Internal mutable record — never escapes the class.
@dataclasses.dataclass(slots=True)
class _SymbolRecord:
    ts_ns: int
    available_liquidity: float  # [0.0, 1.0]


class LiquidityDecay:
    """REFL-02 per-symbol liquidity-decay state machine.

    Pure state machine — no PRNG, no wall-clock reads.  Thread-safety is
    NOT guaranteed; use one instance per simulation thread or wrap access
    with an external lock if sharing across threads.

    Usage::

        params = LiquidityDecayParams(decay_rate_per_unit=0.05,
                                       replenish_rate_per_ns=1e-12)
        ld = LiquidityDecay(params=params)
        state = ld.consume("BTC-USD", qty=10.0, ts_ns=1_000_000_000)
        state = ld.replenish("BTC-USD", ts_ns=2_000_000_000_000)
        liq = ld.current("BTC-USD")
    """

    __slots__ = ("_params", "_state")

    def __init__(self, params: LiquidityDecayParams) -> None:
        if not isinstance(params, LiquidityDecayParams):
            raise TypeError(
                f"LiquidityDecay.params must be LiquidityDecayParams, got {type(params).__name__}"
            )
        self._params: LiquidityDecayParams = params
        self._state: dict[str, _SymbolRecord] = {}

    @property
    def params(self) -> LiquidityDecayParams:
        return self._params

    def _get_or_create(self, symbol: str, ts_ns: int) -> _SymbolRecord:
        """Return existing record or create a fully-liquid one."""
        if symbol not in self._state:
            self._state[symbol] = _SymbolRecord(ts_ns=ts_ns, available_liquidity=1.0)
        return self._state[symbol]

    def consume(self, symbol: str, qty: float, ts_ns: int) -> LiquidityState:
        """Consume ``qty`` units of liquidity for ``symbol`` at ``ts_ns``.

        Removes ``qty * params.decay_rate_per_unit`` from available liquidity,
        clamping the result to [0.0, 1.0].

        Args:
            symbol: Instrument identifier (non-empty).
            qty: Units consumed (>= 0; negative treated as 0).
            ts_ns: Caller-supplied timestamp in nanoseconds (>= 0).

        Returns:
            Frozen :class:`LiquidityState` after consumption.
        """
        if not symbol:
            raise ValueError("LiquidityDecay.consume: symbol must be non-empty")
        if ts_ns < 0:
            raise ValueError(f"LiquidityDecay.consume: ts_ns must be >= 0, got {ts_ns!r}")
        qty = max(0.0, qty)
        record = self._get_or_create(symbol, ts_ns)
        removed = qty * self._params.decay_rate_per_unit
        record.available_liquidity = max(0.0, min(1.0, record.available_liquidity - removed))
        record.ts_ns = ts_ns
        return LiquidityState(
            ts_ns=record.ts_ns,
            symbol=symbol,
            available_liquidity=record.available_liquidity,
        )

    def replenish(self, symbol: str, ts_ns: int) -> LiquidityState:
        """Replenish liquidity for ``symbol`` based on elapsed time since
        the last update.

        Adds ``delta_ns * params.replenish_rate_per_ns`` to available
        liquidity, clamped to [0.0, 1.0].  If the symbol has no recorded
        state, starts at 1.0 (fully liquid) and returns immediately.

        Args:
            symbol: Instrument identifier (non-empty).
            ts_ns: Caller-supplied timestamp in nanoseconds (>= 0).

        Returns:
            Frozen :class:`LiquidityState` after replenishment.
        """
        if not symbol:
            raise ValueError("LiquidityDecay.replenish: symbol must be non-empty")
        if ts_ns < 0:
            raise ValueError(f"LiquidityDecay.replenish: ts_ns must be >= 0, got {ts_ns!r}")
        record = self._get_or_create(symbol, ts_ns)
        delta_ns = max(0, ts_ns - record.ts_ns)
        restored = delta_ns * self._params.replenish_rate_per_ns
        record.available_liquidity = max(0.0, min(1.0, record.available_liquidity + restored))
        record.ts_ns = ts_ns
        return LiquidityState(
            ts_ns=record.ts_ns,
            symbol=symbol,
            available_liquidity=record.available_liquidity,
        )

    def current(self, symbol: str) -> float:
        """Return the current available liquidity fraction for ``symbol``.

        Returns 1.0 (fully liquid) if the symbol has never been seen.
        Does NOT apply any time-based replenishment — call :meth:`replenish`
        first if you need that.

        Args:
            symbol: Instrument identifier.

        Returns:
            Current ``available_liquidity`` in [0.0, 1.0].
        """
        record = self._state.get(symbol)
        if record is None:
            return 1.0
        return record.available_liquidity
