"""SIM-15 stop_hunter — adversarial stop-hunting simulation.

Simulates a price spike that triggers stop orders, then partially recovers.
Models the hostile-market-maker pattern that pushes price through a known
stop-loss cluster to harvest forced liquidations before mean-reverting.

This module is self-contained and does NOT share state with the top-level
``simulation/stop_hunter.py`` (SIM-08), which operates on
:class:`~core.contracts.simulation.RealityScenario` objects.  This module
provides a standalone dataclass-based API for the adversarial subsystem.

Authority constraints
---------------------
* OFFLINE tier — no imports from intelligence_engine, execution_engine,
  governance_engine, evolution_engine, or learning_engine.
* B27/B28/INV-71 — does NOT construct SignalEvent, ExecutionEvent,
  HazardEvent, or PatchProposal.
* INV-15 — pure function; ts_ns, mid_price, and seed supplied by caller.

INV-15 (replay determinism)
---------------------------
Two calls with identical ``(params, symbol, ts_ns, mid_price)`` produce
byte-identical :class:`StopHuntResult` outputs.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random


__all__ = [
    "StopHuntParams",
    "StopHuntResult",
    "StopHunter",
]

_DIGEST_SIZE = 16  # BLAKE2b-128


@dataclasses.dataclass(frozen=True, slots=True)
class StopHuntParams:
    """Configuration for a single stop-hunt simulation run.

    Attributes:
        spike_pct: Price spike magnitude as a fraction of mid price.
            E.g. 0.02 = 2% spike.  Must be in [0.0, 1.0].
        recovery_pct: Fraction of the spike that is recovered.
            0.0 = no recovery; 1.0 = full reversion to mid price.
            Must be in [0.0, 1.0].
        seed: PRNG seed for determinism.
    """

    spike_pct: float
    recovery_pct: float
    seed: int

    def __post_init__(self) -> None:
        if not 0.0 <= self.spike_pct <= 1.0:
            raise ValueError(
                f"StopHuntParams.spike_pct must be in [0.0, 1.0], got {self.spike_pct!r}"
            )
        if not 0.0 <= self.recovery_pct <= 1.0:
            raise ValueError(
                f"StopHuntParams.recovery_pct must be in [0.0, 1.0], got {self.recovery_pct!r}"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class StopHuntResult:
    """Outcome of one stop-hunt simulation.

    Attributes:
        ts_ns: Caller-supplied simulation timestamp (nanoseconds).
        symbol: Instrument identifier.
        trigger_price: Mid price at the time of the hunt (= input mid_price).
        spike_price: Price reached at the spike peak.
        recovery_price: Price after partial recovery.
        stops_triggered_est: Estimated number of stop orders triggered (1–50).
        digest: BLAKE2b-128 hex digest over canonical JSON for integrity.
    """

    ts_ns: int
    symbol: str
    trigger_price: float
    spike_price: float
    recovery_price: float
    stops_triggered_est: int
    digest: str


def _canonical_json(
    ts_ns: int,
    symbol: str,
    trigger_price: float,
    spike_price: float,
    recovery_price: float,
    stops_triggered_est: int,
) -> bytes:
    doc = {
        "ts_ns": ts_ns,
        "symbol": symbol,
        "trigger_price": trigger_price,
        "spike_price": spike_price,
        "recovery_price": recovery_price,
        "stops_triggered_est": stops_triggered_est,
    }
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _blake2b_128(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=_DIGEST_SIZE).hexdigest()


class StopHunter:
    """SIM-15 adversarial stop-hunting simulator.

    Pure — no I/O, no wall-clock reads.  All randomness is seeded from
    ``params.seed`` so identical inputs produce identical outputs (INV-15).

    Usage::

        params = StopHuntParams(spike_pct=0.02, recovery_pct=0.5, seed=7)
        hunter = StopHunter(params=params)
        result = hunter.simulate("ETH-USD", ts_ns=1_700_000_000_000_000_000, mid_price=2000.0)
    """

    __slots__ = ("_params",)

    def __init__(self, params: StopHuntParams) -> None:
        if not isinstance(params, StopHuntParams):
            raise TypeError(
                f"StopHunter.params must be StopHuntParams, got {type(params).__name__}"
            )
        self._params = params

    @property
    def params(self) -> StopHuntParams:
        return self._params

    def simulate(self, symbol: str, ts_ns: int, mid_price: float) -> StopHuntResult:
        """Run a deterministic stop-hunt simulation.

        Args:
            symbol: Instrument identifier (non-empty).
            ts_ns: Caller-supplied simulation timestamp in nanoseconds (>= 0).
            mid_price: Mid-market price at which the hunt begins (> 0).

        Returns:
            Frozen :class:`StopHuntResult` with BLAKE2b-128 digest.

        Raises:
            ValueError: When arguments are malformed.
        """
        if not symbol:
            raise ValueError("StopHunter.simulate: symbol must be non-empty")
        if ts_ns < 0:
            raise ValueError(f"StopHunter.simulate: ts_ns must be >= 0, got {ts_ns!r}")
        if not mid_price > 0.0:
            raise ValueError(
                f"StopHunter.simulate: mid_price must be > 0, got {mid_price!r}"
            )

        params = self._params
        rng = random.Random(params.seed)

        # Price spikes downward (assumes long stop hunt — longs get stopped out).
        spike_price = mid_price * (1.0 - params.spike_pct)
        spike_price = max(0.0, spike_price)

        # Partial recovery toward mid price.
        recovery_price = spike_price + params.recovery_pct * (mid_price - spike_price)

        # Deterministic stop count estimate in [1, 50].
        stops_triggered_est = rng.randint(1, 50)

        payload = _canonical_json(
            ts_ns, symbol, mid_price, spike_price, recovery_price, stops_triggered_est
        )
        digest = _blake2b_128(payload)

        return StopHuntResult(
            ts_ns=ts_ns,
            symbol=symbol,
            trigger_price=mid_price,
            spike_price=spike_price,
            recovery_price=recovery_price,
            stops_triggered_est=stops_triggered_est,
            digest=digest,
        )
