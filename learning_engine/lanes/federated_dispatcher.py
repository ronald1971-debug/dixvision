"""C-13 — Federated learning lane dispatcher (OFFLINE_ONLY).

Routes a federated training request to the appropriate lane based on the
caller-supplied :class:`FederatedLaneType`:

* ``FLAT``         — C-09 Flower FedAvg (single round, single parameter).
* ``HIERARCHICAL`` — C-10 FedML hierarchical two-tier aggregation.
* ``RING``         — C-10 FedML ring (sequential) aggregation.
* ``PLAN``         — C-11 OpenFL declarative multi-round plan.
* ``PRIVATE``      — C-12 PySyft differential-privacy round.

All lanes ultimately call C-09 ``fed_avg_aggregate`` and return a
``(aggregate_record, LearningUpdate)`` pair; the dispatcher normalises
the return shapes so callers do not need to import individual lanes.

Authority + safety constraints (mirrors C-09 / C-10 / C-11 / C-12):

* **L2 / B1.** OFFLINE-only. No runtime-tier imports. No top-level
  ``flwr`` / ``fedml`` / ``openfl`` / ``syft`` / ``time`` /
  ``datetime`` / ``random`` / ``asyncio`` / ``os`` / ``numpy`` /
  ``torch`` / ``polars`` / ``requests`` / ``httpx`` / ``sqlite3``.
* **INV-15.** Pure / deterministic. Aggregation order is canonicalised
  by each lane's own sort key; the dispatcher does not add further
  non-determinism.
* **B27 / B28 / INV-71.** Never constructs transport-layer typed events.
  Produces a domain :class:`~core.contracts.learning.LearningUpdate`
  only; the existing :class:`~learning_engine.update_emitter.UpdateEmitter`
  is the sole transport-layer constructor.
* **Privacy.** Per-client contributions pass through C-09's
  :func:`~learning_engine.lanes.federated.verify_privacy`. C-12
  additionally applies calibrated DP noise.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from core.contracts.learning import LearningUpdate
from learning_engine.lanes.federated import (
    FederatedAggregate,
    GradientUpdate,
    aggregate_round,
)

__all__ = [
    "DISPATCHER_VERSION",
    "FederatedLaneType",
    "FederatedDispatchResult",
    "FederatedLaneDispatcher",
    "dispatch_federated_round",
]

DISPATCHER_VERSION: str = "v1.0-C13"


# ---------------------------------------------------------------------------
# Lane type enum
# ---------------------------------------------------------------------------


class FederatedLaneType(StrEnum):
    """Federated learning lane routing key.

    * ``FLAT``         — C-09 single-round FedAvg (default).
    * ``HIERARCHICAL`` — C-10 two-tier hierarchical aggregation.
    * ``RING``         — C-10 ring sequential fold.
    * ``PLAN``         — C-11 multi-round OpenFL plan.
    * ``PRIVATE``      — C-12 differential-privacy PySyft round.
    """

    FLAT = "flat"
    HIERARCHICAL = "hierarchical"
    RING = "ring"
    PLAN = "plan"
    PRIVATE = "private"


# ---------------------------------------------------------------------------
# Result value object
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class FederatedDispatchResult:
    """Normalised result of one federated dispatch.

    Fields:
        lane:           :class:`FederatedLaneType` that processed the request.
        aggregate:      The primary :class:`FederatedAggregate` produced (or
                        the root aggregate for hierarchical / ring / plan).
        learning_update: Domain :class:`~core.contracts.learning.LearningUpdate`
                        ready for :class:`~learning_engine.update_emitter.UpdateEmitter`.
        extra:          Lane-specific structured records (e.g. per-group
                        aggregates for HIERARCHICAL, per-round reports for
                        PLAN, privacy accountant for PRIVATE). Callers that
                        want lane-specific detail can inspect ``extra``.
    """

    lane: FederatedLaneType
    aggregate: FederatedAggregate
    learning_update: LearningUpdate
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class FederatedLaneDispatcher:
    """Route a federated learning request to the correct lane.

    The dispatcher is stateless between calls — it holds no per-round
    state. All state required by the lanes (current parameter values,
    round IDs, privacy budgets) must be supplied by the caller.

    Usage::

        dispatcher = FederatedLaneDispatcher()
        result = dispatcher.dispatch(
            lane=FederatedLaneType.FLAT,
            round_id="r-001",
            strategy_id="ewc-v1",
            parameter="alpha",
            current_value=0.42,
            updates=[GradientUpdate(...)],
            ts_ns=time.time_ns(),
        )
        emitter.emit(result.learning_update)
    """

    def dispatch(
        self,
        *,
        lane: FederatedLaneType,
        round_id: str,
        strategy_id: str,
        parameter: str,
        current_value: float,
        updates: Sequence[GradientUpdate],
        ts_ns: int,
        # HIERARCHICAL-only
        group_assignments: Any = None,
        # PLAN-only
        plan: Any = None,
        plan_contributions: Any = None,
        initial_value: float | None = None,
        # PRIVATE-only
        privacy_budget: Any = None,
        noise_config: Any = None,
        privacy_accountant: Any = None,
        private_contributions: Any = None,
        # shared
        min_clients: int = 2,
    ) -> FederatedDispatchResult:
        """Route the request to the correct lane and return a normalised result.

        Args:
            lane: Which federated lane to use.
            round_id: Caller-supplied unique round identifier.
            strategy_id: Strategy identifier for the :class:`LearningUpdate`.
            parameter: Name of the parameter being updated.
            current_value: Current parameter value before this round.
            updates: Per-client :class:`GradientUpdate` contributions.
            ts_ns: Caller-supplied monotone event-time (nanoseconds).
            group_assignments: Required for ``HIERARCHICAL`` — sequence of
                :class:`~learning_engine.lanes.federated_fedml.GroupAssignment`.
            plan: Required for ``PLAN`` — a
                :class:`~learning_engine.lanes.federated_openfl.FederationPlan`.
            plan_contributions: Required for ``PLAN`` — per-round contributions.
            initial_value: Used by ``PLAN``; defaults to ``current_value``.
            privacy_budget: Required for ``PRIVATE`` — a
                :class:`~learning_engine.lanes.federated_pysyft.PrivacyBudget`.
            noise_config: Required for ``PRIVATE`` — a
                :class:`~learning_engine.lanes.federated_pysyft.NoiseConfig`.
            privacy_accountant: Required for ``PRIVATE`` — the current
                :class:`~learning_engine.lanes.federated_pysyft.PrivacyAccountant`.
            private_contributions: Required for ``PRIVATE`` — sequence of
                :class:`~learning_engine.lanes.federated_pysyft.PrivateContribution`.
            min_clients: Minimum distinct clients required per round
                (passed to the lane that validates the round).

        Returns:
            :class:`FederatedDispatchResult` with normalised aggregate and
            learning update.

        Raises:
            ValueError: Missing required lane-specific arguments, or the lane
                raises on an invalid round.
            TypeError: Wrong argument types.
        """
        if not isinstance(lane, FederatedLaneType):
            try:
                lane = FederatedLaneType(lane)
            except ValueError:
                raise TypeError(
                    f"FederatedLaneDispatcher.dispatch: lane must be a"
                    f" FederatedLaneType, got {lane!r}"
                )

        if lane is FederatedLaneType.FLAT:
            return self._dispatch_flat(
                round_id=round_id,
                strategy_id=strategy_id,
                parameter=parameter,
                current_value=current_value,
                updates=updates,
                ts_ns=ts_ns,
                min_clients=min_clients,
            )

        if lane is FederatedLaneType.HIERARCHICAL:
            return self._dispatch_hierarchical(
                round_id=round_id,
                strategy_id=strategy_id,
                parameter=parameter,
                current_value=current_value,
                updates=updates,
                ts_ns=ts_ns,
                group_assignments=group_assignments,
                min_clients=min_clients,
            )

        if lane is FederatedLaneType.RING:
            return self._dispatch_ring(
                round_id=round_id,
                strategy_id=strategy_id,
                parameter=parameter,
                current_value=current_value,
                updates=updates,
                ts_ns=ts_ns,
                min_clients=min_clients,
            )

        if lane is FederatedLaneType.PLAN:
            return self._dispatch_plan(
                strategy_id=strategy_id,
                plan=plan,
                plan_contributions=plan_contributions,
                initial_value=initial_value if initial_value is not None else current_value,
                ts_ns=ts_ns,
            )

        if lane is FederatedLaneType.PRIVATE:
            return self._dispatch_private(
                round_id=round_id,
                strategy_id=strategy_id,
                parameter=parameter,
                current_value=current_value,
                privacy_budget=privacy_budget,
                noise_config=noise_config,
                privacy_accountant=privacy_accountant,
                private_contributions=private_contributions,
                ts_ns=ts_ns,
            )

        raise TypeError(f"unhandled lane type: {lane!r}")  # pragma: no cover

    # ------------------------------------------------------------------
    # Lane implementations
    # ------------------------------------------------------------------

    def _dispatch_flat(
        self, *, round_id: str, strategy_id: str, parameter: str,
        current_value: float, updates: Sequence[GradientUpdate],
        ts_ns: int, min_clients: int,
    ) -> FederatedDispatchResult:
        """C-09 single-round FedAvg."""
        agg, lu = aggregate_round(
            round_id=round_id,
            strategy_id=strategy_id,
            parameter=parameter,
            current_value=current_value,
            updates=updates,
            ts_ns=ts_ns,
            min_clients=min_clients,
        )
        return FederatedDispatchResult(
            lane=FederatedLaneType.FLAT,
            aggregate=agg,
            learning_update=lu,
        )

    def _dispatch_hierarchical(
        self, *, round_id: str, strategy_id: str, parameter: str,
        current_value: float, updates: Sequence[GradientUpdate],
        ts_ns: int, group_assignments: Any, min_clients: int,
    ) -> FederatedDispatchResult:
        """C-10 FedML hierarchical aggregation.

        ``hierarchical_aggregate`` returns ``(HierarchicalRoundResult,
        LearningUpdate)``. The root aggregate is at
        ``result.root_aggregate``.
        """
        from learning_engine.lanes.federated_fedml import hierarchical_aggregate

        if group_assignments is None:
            raise ValueError(
                "FederatedLaneDispatcher: group_assignments is required for HIERARCHICAL lane"
            )
        result, lu = hierarchical_aggregate(
            round_id=round_id,
            strategy_id=strategy_id,
            parameter=parameter,
            current_value=current_value,
            updates=updates,
            groups=group_assignments,
            ts_ns=ts_ns,
        )
        return FederatedDispatchResult(
            lane=FederatedLaneType.HIERARCHICAL,
            aggregate=result.root_aggregate,
            learning_update=lu,
            extra={"group_aggregates": result.group_aggregates, "result": result},
        )

    def _dispatch_ring(
        self, *, round_id: str, strategy_id: str, parameter: str,
        current_value: float, updates: Sequence[GradientUpdate],
        ts_ns: int, min_clients: int,
    ) -> FederatedDispatchResult:
        """C-10 FedML ring aggregation.

        ``ring_aggregate`` returns ``(RingRoundResult, LearningUpdate)``.
        ``RingRoundResult`` carries ``aggregated_delta``, ``total_samples``,
        ``digest``, and ``steps`` but no ``final_aggregate`` field — we
        synthesise a :class:`FederatedAggregate` from those fields.
        """
        from learning_engine.lanes.federated import FederatedAggregate
        from learning_engine.lanes.federated_fedml import ring_aggregate

        result, lu = ring_aggregate(
            round_id=round_id,
            strategy_id=strategy_id,
            parameter=parameter,
            current_value=current_value,
            updates=updates,
            ts_ns=ts_ns,
        )
        # Synthesise a FederatedAggregate from RingRoundResult fields.
        n_clients = len(result.ring_order)
        agg = FederatedAggregate(
            round_id=result.round_id,
            parameter=result.parameter,
            n_clients=n_clients,
            aggregated_delta=result.aggregated_delta,
            total_samples=result.total_samples,
            ts_ns=result.ts_ns,
            digest=result.digest,
        )
        return FederatedDispatchResult(
            lane=FederatedLaneType.RING,
            aggregate=agg,
            learning_update=lu,
            extra={"steps": result.steps, "ring_order": result.ring_order, "result": result},
        )

    def _dispatch_plan(
        self, *, strategy_id: str, plan: Any, plan_contributions: Any,
        initial_value: float, ts_ns: int,
    ) -> FederatedDispatchResult:
        """C-11 OpenFL multi-round plan."""
        from learning_engine.lanes.federated_openfl import execute_plan

        if plan is None:
            raise ValueError(
                "FederatedLaneDispatcher: plan is required for PLAN lane"
            )
        if plan_contributions is None:
            raise ValueError(
                "FederatedLaneDispatcher: plan_contributions is required for PLAN lane"
            )
        report, lu = execute_plan(
            plan=plan,
            contributions=plan_contributions,
            initial_value=initial_value,
            ts_ns=ts_ns,
        )
        # Build a FederatedAggregate from the last round's report.
        last_round = report.rounds[-1] if report.rounds else None
        if last_round is None:
            raise ValueError("PLAN dispatch: plan produced zero rounds")

        from learning_engine.lanes.federated import FederatedAggregate

        root_agg = FederatedAggregate(
            round_id=f"{report.plan_id}:round{last_round.round_index}",
            parameter=plan.parameter,
            n_clients=last_round.n_collaborators,
            aggregated_delta=last_round.aggregated_delta,
            total_samples=last_round.total_samples,
            ts_ns=ts_ns,
            digest=last_round.digest,
        )
        return FederatedDispatchResult(
            lane=FederatedLaneType.PLAN,
            aggregate=root_agg,
            learning_update=lu,
            extra={"report": report},
        )

    def _dispatch_private(
        self, *, round_id: str, strategy_id: str, parameter: str,
        current_value: float, privacy_budget: Any, noise_config: Any,
        privacy_accountant: Any, private_contributions: Any, ts_ns: int,
    ) -> FederatedDispatchResult:
        """C-12 PySyft differential-privacy round.

        ``aggregate_private_round`` takes already-noised
        :class:`~learning_engine.lanes.federated_pysyft.PrivateContribution`
        objects (``private_contributions``) plus the running
        ``privacy_accountant``. The caller is responsible for creating
        ``PrivateContribution`` objects via
        :func:`~learning_engine.lanes.federated_pysyft.apply_dp_noise`
        using ``privacy_budget`` and ``noise_config`` before calling
        ``dispatch``. Those two parameters are stored in ``extra`` so the
        caller can reconstruct the round context.

        Returns ``(report, learning_update, next_accountant)`` from the
        lane; the dispatcher normalises to :class:`FederatedDispatchResult`.
        """
        from learning_engine.lanes.federated import FederatedAggregate
        from learning_engine.lanes.federated_pysyft import aggregate_private_round

        if privacy_accountant is None:
            raise ValueError(
                "FederatedLaneDispatcher: privacy_accountant is required for PRIVATE lane"
            )
        if private_contributions is None:
            raise ValueError(
                "FederatedLaneDispatcher: private_contributions is required for PRIVATE lane"
            )

        report, lu, new_accountant = aggregate_private_round(
            round_id=round_id,
            strategy_id=strategy_id,
            parameter=parameter,
            current_value=current_value,
            accountant=privacy_accountant,
            contributions=private_contributions,
            ts_ns=ts_ns,
        )
        agg = FederatedAggregate(
            round_id=round_id,
            parameter=parameter,
            n_clients=report.n_clients,
            aggregated_delta=report.aggregated_delta,
            total_samples=report.total_samples,
            ts_ns=ts_ns,
            digest=report.digest,
        )
        return FederatedDispatchResult(
            lane=FederatedLaneType.PRIVATE,
            aggregate=agg,
            learning_update=lu,
            extra={
                "report": report,
                "new_accountant": new_accountant,
                "epsilon_spent": report.epsilon_spent,
                "delta_spent": report.delta_spent,
                # Caller context preserved for auditability.
                "privacy_budget": privacy_budget,
                "noise_config": noise_config,
            },
        )

    def is_active(self) -> bool:
        """Return ``True`` — the dispatcher is always ready.

        Wired as the ``is_active_fn`` for :class:`LearningEngine` so
        the engine health check reports OK when the dispatcher is
        instantiated (i.e. the federated lane is structurally live).
        Individual round failures are surfaced through the caller's
        exception handling, not through the health state.
        """
        return True


# ---------------------------------------------------------------------------
# Module-level convenience wrapper
# ---------------------------------------------------------------------------


def dispatch_federated_round(
    *,
    lane: FederatedLaneType | str = FederatedLaneType.FLAT,
    **kwargs: Any,
) -> FederatedDispatchResult:
    """Convenience one-call wrapper around :class:`FederatedLaneDispatcher`.

    Creates a fresh dispatcher and delegates. Caller-supplied keyword
    arguments are forwarded verbatim to :meth:`FederatedLaneDispatcher.dispatch`.
    """
    return FederatedLaneDispatcher().dispatch(lane=lane, **kwargs)  # type: ignore[arg-type]
