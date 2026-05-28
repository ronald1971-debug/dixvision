"""SIM-14 liquidity_attacker — adversarial liquidity removal simulation.

Models an attacker who removes a fraction of the visible order-book depth
to induce slippage on subsequent orders. The simulator is fully deterministic
given a caller-supplied seed; it performs no I/O and reads no wall clock.

Authority constraints
---------------------
* OFFLINE tier — no imports from intelligence_engine, execution_engine,
  governance_engine, evolution_engine, or learning_engine.
* B27/B28/INV-71 — does NOT construct SignalEvent, ExecutionEvent,
  HazardEvent, or PatchProposal.
* INV-15 — pure function; ts_ns and seed supplied by caller.

INV-15 (replay determinism)
---------------------------
Two calls with identical ``(params, symbol, ts_ns)`` produce byte-identical
:class:`LiquidityAttackResult` outputs including the BLAKE2b-128 digest.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random


__all__ = [
    "LiquidityAttackParams",
    "LiquidityAttackResult",
    "LiquidityAttacker",
]

_DIGEST_SIZE = 16  # BLAKE2b-128 = 16 bytes = 32 hex chars


@dataclasses.dataclass(frozen=True, slots=True)
class LiquidityAttackParams:
    """Configuration for a single liquidity-attack simulation run.

    Attributes:
        attack_depth_pct: Fraction of the visible order-book depth to remove.
            Must be in [0.0, 1.0]. 0.0 = no removal; 1.0 = full book removal.
        duration_ns: Simulated attack duration in nanoseconds (>= 0).
        seed: PRNG seed for determinism.  Two calls with identical params
            and ts_ns always produce identical results.
    """

    attack_depth_pct: float
    duration_ns: int
    seed: int

    def __post_init__(self) -> None:
        if not 0.0 <= self.attack_depth_pct <= 1.0:
            raise ValueError(
                "LiquidityAttackParams.attack_depth_pct must be in [0.0, 1.0], "
                f"got {self.attack_depth_pct!r}"
            )
        if self.duration_ns < 0:
            raise ValueError(
                f"LiquidityAttackParams.duration_ns must be >= 0, got {self.duration_ns!r}"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class LiquidityAttackResult:
    """Outcome of one adversarial liquidity-removal simulation.

    Attributes:
        ts_ns: Caller-supplied simulation timestamp (nanoseconds).
        symbol: Instrument identifier.
        depth_removed_pct: Realised fraction of depth removed
            (sampled from [0, attack_depth_pct]).
        slippage_multiplier: Resulting slippage multiplier on subsequent
            orders.  Always >= 1.0.
        digest: BLAKE2b-128 hex digest over canonical JSON of this result
            (excluding the digest field itself) for integrity verification.
    """

    ts_ns: int
    symbol: str
    depth_removed_pct: float
    slippage_multiplier: float
    digest: str


def _canonical_json(ts_ns: int, symbol: str, depth_removed_pct: float,
                    slippage_multiplier: float) -> bytes:
    """Return a stable UTF-8 JSON encoding for hashing."""
    doc = {
        "ts_ns": ts_ns,
        "symbol": symbol,
        "depth_removed_pct": depth_removed_pct,
        "slippage_multiplier": slippage_multiplier,
    }
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _blake2b_128(data: bytes) -> str:
    """Return BLAKE2b-128 hex digest (32 hex characters)."""
    h = hashlib.blake2b(data, digest_size=_DIGEST_SIZE)
    return h.hexdigest()


class LiquidityAttacker:
    """SIM-14 adversarial liquidity-removal simulator.

    Pure — performs no I/O and reads no wall clock.  All randomness is
    seeded from ``params.seed`` so identical inputs produce identical
    outputs (INV-15).

    Usage::

        params = LiquidityAttackParams(attack_depth_pct=0.4, duration_ns=5_000_000, seed=42)
        attacker = LiquidityAttacker(params=params)
        result = attacker.simulate(symbol="BTC-USD", ts_ns=1_700_000_000_000_000_000)
    """

    __slots__ = ("_params",)

    def __init__(self, params: LiquidityAttackParams) -> None:
        if not isinstance(params, LiquidityAttackParams):
            raise TypeError(
                f"LiquidityAttacker.params must be LiquidityAttackParams, "
                f"got {type(params).__name__}"
            )
        self._params = params

    @property
    def params(self) -> LiquidityAttackParams:
        return self._params

    def simulate(self, symbol: str, ts_ns: int) -> LiquidityAttackResult:
        """Run a deterministic adversarial liquidity-removal simulation.

        Args:
            symbol: Instrument identifier (non-empty).
            ts_ns: Caller-supplied simulation timestamp in nanoseconds (>= 0).

        Returns:
            Frozen :class:`LiquidityAttackResult` with BLAKE2b-128 digest.

        Raises:
            ValueError: When arguments are malformed.
        """
        if not symbol:
            raise ValueError("LiquidityAttacker.simulate: symbol must be non-empty")
        if ts_ns < 0:
            raise ValueError(
                f"LiquidityAttacker.simulate: ts_ns must be >= 0, got {ts_ns!r}"
            )

        params = self._params
        rng = random.Random(params.seed)

        # Realised depth removal: uniform in [0, attack_depth_pct].
        depth_removed_pct = rng.uniform(0.0, params.attack_depth_pct)

        # Random factor in [0.5, 2.0] for the slippage amplification.
        random_factor = rng.uniform(0.5, 2.0)

        # Slippage multiplier: 1 + depth_removed * random_factor.
        # Always >= 1.0 because depth_removed_pct >= 0 and random_factor >= 0.
        slippage_multiplier = 1.0 + depth_removed_pct * random_factor

        payload = _canonical_json(ts_ns, symbol, depth_removed_pct, slippage_multiplier)
        digest = _blake2b_128(payload)

        return LiquidityAttackResult(
            ts_ns=ts_ns,
            symbol=symbol,
            depth_removed_pct=depth_removed_pct,
            slippage_multiplier=slippage_multiplier,
            digest=digest,
        )
