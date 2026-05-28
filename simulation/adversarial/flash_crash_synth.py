"""SIM-16 flash_crash_synth — synthetic flash-crash generator.

Produces a crash-and-recovery price series (a sequence of
:class:`FlashCrashBar` records) for use in adversarial stress-testing.
Unlike the top-level ``simulation/flash_crash_synth.py`` (SIM-09) which
operates on :class:`~core.contracts.simulation.RealityScenario` objects,
this module exposes a clean bar-series API suitable for feeding into
tick-replay or intra-bar simulation pipelines.

The crash phase drives price down by up to ``crash_pct``; the recovery
phase drives price back up by up to ``recovery_pct`` of the crash.
Both phases are shaped with per-bar Gaussian-like noise drawn from the
seeded PRNG so the bars look realistic but are fully deterministic.

Authority constraints
---------------------
* OFFLINE tier — no imports from intelligence_engine, execution_engine,
  governance_engine, evolution_engine, or learning_engine.
* B27/B28/INV-71 — does NOT construct SignalEvent, ExecutionEvent,
  HazardEvent, or PatchProposal.
* INV-15 — pure function; ts_ns and seed supplied by caller.

INV-15 (replay determinism)
---------------------------
Two calls with identical ``(params, symbol, ts_ns, start_price)`` produce
byte-identical :class:`FlashCrashResult` outputs.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random


__all__ = [
    "FlashCrashParams",
    "FlashCrashBar",
    "FlashCrashResult",
    "FlashCrashSynth",
]

_DIGEST_SIZE = 16  # BLAKE2b-128


@dataclasses.dataclass(frozen=True, slots=True)
class FlashCrashParams:
    """Configuration for a single flash-crash generation run.

    Attributes:
        crash_pct: Maximum price drop as a fraction of start_price.
            E.g. 0.10 = 10% drop.  Must be in [0.0, 1.0].
        recovery_pct: Maximum recovery as a fraction of the crash depth.
            E.g. 0.08 = 80% of a 10% crash ≈ 8% recovery.
            Must be in [0.0, 1.0].
        duration_bars: Total number of bars to generate (crash + recovery).
            Must be >= 2 (at least one crash bar and one recovery bar).
        seed: PRNG seed for determinism.
    """

    crash_pct: float
    recovery_pct: float
    duration_bars: int
    seed: int

    def __post_init__(self) -> None:
        if not 0.0 <= self.crash_pct <= 1.0:
            raise ValueError(
                f"FlashCrashParams.crash_pct must be in [0.0, 1.0], got {self.crash_pct!r}"
            )
        if not 0.0 <= self.recovery_pct <= 1.0:
            raise ValueError(
                f"FlashCrashParams.recovery_pct must be in [0.0, 1.0], got {self.recovery_pct!r}"
            )
        if self.duration_bars < 2:
            raise ValueError(
                f"FlashCrashParams.duration_bars must be >= 2, got {self.duration_bars!r}"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class FlashCrashBar:
    """One price bar in the synthetic flash-crash series.

    Attributes:
        bar_index: Zero-based position in the series.
        price: Mid price for this bar.
        volume_multiplier: Relative volume vs. normal; crash bars typically
            have volume_multiplier > 1 (panic selling), recovery bars
            somewhat lower.
    """

    bar_index: int
    price: float
    volume_multiplier: float


@dataclasses.dataclass(frozen=True, slots=True)
class FlashCrashResult:
    """Outcome of one synthetic flash-crash generation.

    Attributes:
        ts_ns: Caller-supplied simulation timestamp (nanoseconds).
        symbol: Instrument identifier.
        bars: Immutable sequence of :class:`FlashCrashBar` records in order.
        nadir_price: Lowest price reached across all bars.
        nadir_bar: bar_index of the bar containing nadir_price.
        digest: BLAKE2b-128 hex digest over canonical JSON for integrity.
    """

    ts_ns: int
    symbol: str
    bars: tuple[FlashCrashBar, ...]
    nadir_price: float
    nadir_bar: int
    digest: str


def _canonical_json(
    ts_ns: int,
    symbol: str,
    bars: tuple[FlashCrashBar, ...],
    nadir_price: float,
    nadir_bar: int,
) -> bytes:
    bar_list = [
        {"bar_index": b.bar_index, "price": b.price, "volume_multiplier": b.volume_multiplier}
        for b in bars
    ]
    doc = {
        "ts_ns": ts_ns,
        "symbol": symbol,
        "bars": bar_list,
        "nadir_price": nadir_price,
        "nadir_bar": nadir_bar,
    }
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _blake2b_128(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=_DIGEST_SIZE).hexdigest()


class FlashCrashSynth:
    """SIM-16 synthetic flash-crash bar-series generator.

    Pure — no I/O, no wall-clock reads.  All randomness is seeded from
    ``params.seed`` so identical inputs produce identical bar series (INV-15).

    The series is split evenly into a crash phase (first half of bars) and
    a recovery phase (second half).  Per-bar noise is drawn from
    ``rng.gauss(0, 0.3)`` so consecutive bars have realistic jaggedness
    without making the overall crash/recovery shape indeterminate.

    Usage::

        params = FlashCrashParams(crash_pct=0.10, recovery_pct=0.08,
                                   duration_bars=20, seed=99)
        synth = FlashCrashSynth(params=params)
        result = synth.simulate("SPY", ts_ns=1_700_000_000_000_000_000, start_price=450.0)
    """

    __slots__ = ("_params",)

    def __init__(self, params: FlashCrashParams) -> None:
        if not isinstance(params, FlashCrashParams):
            raise TypeError(
                f"FlashCrashSynth.params must be FlashCrashParams, got {type(params).__name__}"
            )
        self._params = params

    @property
    def params(self) -> FlashCrashParams:
        return self._params

    def simulate(
        self, symbol: str, ts_ns: int, start_price: float
    ) -> FlashCrashResult:
        """Generate a deterministic flash-crash bar series.

        Args:
            symbol: Instrument identifier (non-empty).
            ts_ns: Caller-supplied simulation timestamp in nanoseconds (>= 0).
            start_price: Starting mid price at bar_index=0 (> 0).

        Returns:
            Frozen :class:`FlashCrashResult` with full bar series and
            BLAKE2b-128 digest.

        Raises:
            ValueError: When arguments are malformed.
        """
        if not symbol:
            raise ValueError("FlashCrashSynth.simulate: symbol must be non-empty")
        if ts_ns < 0:
            raise ValueError(
                f"FlashCrashSynth.simulate: ts_ns must be >= 0, got {ts_ns!r}"
            )
        if not start_price > 0.0:
            raise ValueError(
                f"FlashCrashSynth.simulate: start_price must be > 0, got {start_price!r}"
            )

        params = self._params
        rng = random.Random(params.seed)

        n = params.duration_bars
        crash_bars = n // 2
        recovery_bars = n - crash_bars  # absorbs the odd bar if n is odd

        # --- crash phase ---
        # Spread the crash_pct drop across crash_bars steps with noise.
        crash_depth = params.crash_pct * start_price
        nadir_target = start_price - crash_depth

        bars: list[FlashCrashBar] = []
        current_price = start_price

        for i in range(crash_bars):
            # Progress through the crash: t in (0, 1].
            t = (i + 1) / crash_bars
            # Target at this step (linear, then clamped to >= 0).
            step_target = start_price - crash_depth * t
            # Add noise: small Gaussian perturbation.
            noise_factor = 1.0 + rng.gauss(0.0, 0.03)
            price = max(0.0, step_target * noise_factor)
            # Volume spikes during crash: higher near the nadir.
            volume_multiplier = max(0.1, 1.0 + 3.0 * t + rng.uniform(-0.2, 0.2))
            bars.append(FlashCrashBar(bar_index=i, price=price, volume_multiplier=volume_multiplier))
            current_price = price

        # Record nadir from the crash phase.
        nadir_price = min(b.price for b in bars)
        nadir_bar = min(range(len(bars)), key=lambda idx: bars[idx].price)

        # --- recovery phase ---
        # Recover up to recovery_pct of the crash depth.
        recovery_depth = params.recovery_pct * crash_depth
        recovery_target = nadir_price + recovery_depth

        for j in range(recovery_bars):
            bar_index = crash_bars + j
            t = (j + 1) / recovery_bars
            step_target = nadir_price + recovery_depth * t
            noise_factor = 1.0 + rng.gauss(0.0, 0.02)
            price = max(0.0, step_target * noise_factor)
            # Volume subsides during recovery.
            volume_multiplier = max(0.1, 1.5 - 0.5 * t + rng.uniform(-0.1, 0.1))
            bars.append(FlashCrashBar(bar_index=bar_index, price=price, volume_multiplier=volume_multiplier))

        bars_tuple = tuple(bars)

        payload = _canonical_json(ts_ns, symbol, bars_tuple, nadir_price, nadir_bar)
        digest = _blake2b_128(payload)

        return FlashCrashResult(
            ts_ns=ts_ns,
            symbol=symbol,
            bars=bars_tuple,
            nadir_price=nadir_price,
            nadir_bar=nadir_bar,
            digest=digest,
        )
