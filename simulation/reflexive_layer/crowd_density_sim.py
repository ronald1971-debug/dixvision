"""REFL-03 crowd_density_sim — alpha decay due to strategy crowding.

Models the well-documented phenomenon that a strategy's edge (alpha) erodes
as more participants run the same strategy.  When the crowd becomes dense,
the signal is already priced in before our orders execute.

Design
------
* Each unique ``strategy_id`` has a participant count maintained in a dict.
* ``add_participant`` / ``remove_participant`` mutate the count atomically.
* ``simulate`` returns a :class:`CrowdDensityResult` with
  ``alpha_multiplier = max(0.0, 1.0 - count * decay_per_participant)``.
  1.0 = full alpha (no crowding); 0.0 = fully crowded (zero alpha edge).
* Pure state machine — no PRNG, no wall-clock reads.

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
    "CrowdDensityParams",
    "CrowdDensityResult",
    "CrowdDensitySim",
]


@dataclasses.dataclass(frozen=True, slots=True)
class CrowdDensityParams:
    """Configuration for the crowd-density alpha-decay model.

    Attributes:
        decay_per_participant: Alpha reduction per additional participant.
            E.g. 0.05 means each additional participant reduces alpha by 5%.
            Must be in (0.0, 1.0].
        max_participants: Hard cap on tracked participant count per strategy.
            Must be >= 1.
    """

    decay_per_participant: float
    max_participants: int

    def __post_init__(self) -> None:
        if not 0.0 < self.decay_per_participant <= 1.0:
            raise ValueError(
                "CrowdDensityParams.decay_per_participant must be in (0.0, 1.0], "
                f"got {self.decay_per_participant!r}"
            )
        if self.max_participants < 1:
            raise ValueError(
                f"CrowdDensityParams.max_participants must be >= 1, "
                f"got {self.max_participants!r}"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class CrowdDensityResult:
    """Snapshot of crowding-adjusted alpha for one strategy on one symbol.

    Attributes:
        ts_ns: Caller-supplied simulation timestamp (nanoseconds).
        symbol: Instrument identifier.
        strategy_id: Strategy identifier.
        participant_count: Current number of tracked participants running
            this strategy (>= 0, capped at params.max_participants).
        alpha_multiplier: Effective alpha scaling factor.
            1.0 = full alpha (no crowding); 0.0 = fully crowded.
            Always in [0.0, 1.0].
    """

    ts_ns: int
    symbol: str
    strategy_id: str
    participant_count: int
    alpha_multiplier: float


class CrowdDensitySim:
    """REFL-03 strategy-crowding alpha-decay state machine.

    Tracks per-strategy participant counts and computes the resulting
    alpha multiplier on demand.  Pure state machine — no PRNG, no
    wall-clock reads, no I/O.

    Thread-safety: NOT guaranteed.  Use one instance per simulation thread
    or wrap access with an external lock if sharing across threads.

    Usage::

        params = CrowdDensityParams(decay_per_participant=0.1, max_participants=20)
        sim = CrowdDensitySim(params=params)
        sim.add_participant("momentum_v1")
        sim.add_participant("momentum_v1")
        result = sim.simulate("AAPL", "momentum_v1", ts_ns=1_000_000_000)
        # result.alpha_multiplier == max(0.0, 1.0 - 2 * 0.1) == 0.8
    """

    __slots__ = ("_params", "_counts")

    def __init__(self, params: CrowdDensityParams) -> None:
        if not isinstance(params, CrowdDensityParams):
            raise TypeError(
                f"CrowdDensitySim.params must be CrowdDensityParams, got {type(params).__name__}"
            )
        self._params: CrowdDensityParams = params
        self._counts: dict[str, int] = {}

    @property
    def params(self) -> CrowdDensityParams:
        return self._params

    def add_participant(self, strategy_id: str) -> None:
        """Register one additional participant for ``strategy_id``.

        The count is capped at ``params.max_participants``; adding beyond
        the cap is a no-op (no error raised, allowing callers to call
        unconditionally without overflow risk).

        Args:
            strategy_id: Strategy identifier (non-empty).
        """
        if not strategy_id:
            raise ValueError("CrowdDensitySim.add_participant: strategy_id must be non-empty")
        current = self._counts.get(strategy_id, 0)
        self._counts[strategy_id] = min(self._params.max_participants, current + 1)

    def remove_participant(self, strategy_id: str) -> None:
        """Deregister one participant from ``strategy_id``.

        The count is floored at 0; removing from an empty strategy is a
        no-op so callers can deregister unconditionally during cleanup.

        Args:
            strategy_id: Strategy identifier (non-empty).
        """
        if not strategy_id:
            raise ValueError("CrowdDensitySim.remove_participant: strategy_id must be non-empty")
        current = self._counts.get(strategy_id, 0)
        if current > 0:
            self._counts[strategy_id] = current - 1

    def simulate(self, symbol: str, strategy_id: str, ts_ns: int) -> CrowdDensityResult:
        """Compute the crowding-adjusted alpha multiplier.

        ``alpha_multiplier = max(0.0, 1.0 - count * decay_per_participant)``

        Args:
            symbol: Instrument identifier (non-empty).
            strategy_id: Strategy identifier (non-empty).
            ts_ns: Caller-supplied simulation timestamp in nanoseconds (>= 0).

        Returns:
            Frozen :class:`CrowdDensityResult`.

        Raises:
            ValueError: When arguments are malformed.
        """
        if not symbol:
            raise ValueError("CrowdDensitySim.simulate: symbol must be non-empty")
        if not strategy_id:
            raise ValueError("CrowdDensitySim.simulate: strategy_id must be non-empty")
        if ts_ns < 0:
            raise ValueError(f"CrowdDensitySim.simulate: ts_ns must be >= 0, got {ts_ns!r}")

        count = self._counts.get(strategy_id, 0)
        alpha_multiplier = max(0.0, 1.0 - count * self._params.decay_per_participant)

        return CrowdDensityResult(
            ts_ns=ts_ns,
            symbol=symbol,
            strategy_id=strategy_id,
            participant_count=count,
            alpha_multiplier=alpha_multiplier,
        )
