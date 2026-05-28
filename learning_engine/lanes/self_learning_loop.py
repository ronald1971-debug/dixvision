"""Self-supervised learning lane — generates training labels from trade outcomes.

This lane produces its own supervision signal from the system's realised trade
results. When enough trades accumulate and the strategy is profitable enough,
``update()`` derives new parameter values and emits them as ``LearningUpdate``
proposals for governance approval (INV-12).

DIX integration rules:
* OFFLINE-tier only — pure reducer pattern, no clock reads, no IO.
* INV-15: same inputs → same output across replays. Digest pinned by tests.
* INV-12: ``build_learning_updates`` emits proposals; governance approves.
* All mutable state in frozen dataclasses; no global mutation.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from typing import Final

from core.contracts.learning import LearningUpdate

SELF_LEARNING_VERSION: Final[str] = "self-learn.v1"

_ONE_HOUR_NS: Final[int] = 3_600_000_000_000


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SelfLearningError(ValueError):
    """Base error for this lane."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class SelfLearningConfig:
    """Immutable configuration for the self-supervised learning lane.

    Attributes:
        min_trades_per_update: Minimum number of pending records before an
            update may be triggered.
        min_win_rate: Minimum observed win-rate in the pending batch before
            update is allowed.  Guards against learning from a losing period.
        update_cooldown_ns: Minimum nanoseconds between successive updates.
            Prevents over-fitting to short runs.
        version: Algorithm version tag.
    """

    min_trades_per_update: int = 50
    min_win_rate: float = 0.45
    update_cooldown_ns: int = _ONE_HOUR_NS
    version: str = SELF_LEARNING_VERSION

    def __post_init__(self) -> None:
        if self.min_trades_per_update < 1:
            raise SelfLearningError(
                f"min_trades_per_update must be >= 1, got {self.min_trades_per_update}"
            )
        if not (0.0 <= self.min_win_rate <= 1.0):
            raise SelfLearningError(
                f"min_win_rate must be in [0, 1], got {self.min_win_rate}"
            )
        if self.update_cooldown_ns < 0:
            raise SelfLearningError(
                f"update_cooldown_ns must be >= 0, got {self.update_cooldown_ns}"
            )


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class TradeOutcomeRecord:
    """One realised trade packaged for self-supervised labelling.

    Attributes:
        ts_ns: Nanosecond timestamp of the trade close.
        trade_id: Unique trade identifier.
        strategy_id: Strategy that generated this trade.
        direction: ``"LONG"`` or ``"SHORT"``.
        entry_price: Fill price at trade entry.
        exit_price: Fill price at trade exit.
        pnl: Realised profit/loss (signed, in quote currency).
        regime: Regime label at time of trade.
        features: Feature vector recorded at entry decision.
    """

    ts_ns: int
    trade_id: str
    strategy_id: str
    direction: str
    entry_price: float
    exit_price: float
    pnl: float
    regime: str
    features: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.ts_ns <= 0:
            raise SelfLearningError(f"ts_ns must be positive, got {self.ts_ns}")
        if not self.trade_id:
            raise SelfLearningError("trade_id must be non-empty")
        if not self.strategy_id:
            raise SelfLearningError("strategy_id must be non-empty")
        if not math.isfinite(self.entry_price) or self.entry_price <= 0.0:
            raise SelfLearningError(f"entry_price must be finite and > 0, got {self.entry_price}")
        if not math.isfinite(self.exit_price) or self.exit_price <= 0.0:
            raise SelfLearningError(f"exit_price must be finite and > 0, got {self.exit_price}")
        if not math.isfinite(self.pnl):
            raise SelfLearningError(f"pnl must be finite, got {self.pnl}")


@dataclasses.dataclass(frozen=True, slots=True)
class SelfLearningState:
    """Fully serializable state for the self-supervised learning lane.

    Attributes:
        params: Current learned parameter vector (feature weights).
        n_updates: Number of completed update cycles.
        last_update_ts_ns: Timestamp of the most recent update, or ``0``.
        win_rate: Win-rate observed in the last update batch.
        digest: BLAKE2b digest for INV-15 replay verification.
    """

    params: tuple[float, ...]
    n_updates: int
    last_update_ts_ns: int
    win_rate: float
    digest: str

    def __post_init__(self) -> None:
        if self.n_updates < 0:
            raise SelfLearningError(f"n_updates must be >= 0, got {self.n_updates}")
        if self.last_update_ts_ns < 0:
            raise SelfLearningError(
                f"last_update_ts_ns must be >= 0, got {self.last_update_ts_ns}"
            )
        if not (0.0 <= self.win_rate <= 1.0):
            raise SelfLearningError(f"win_rate must be in [0, 1], got {self.win_rate}")


# ---------------------------------------------------------------------------
# Digest helpers
# ---------------------------------------------------------------------------


def _compute_digest(params: tuple[float, ...], n_updates: int, last_update_ts_ns: int) -> str:
    """BLAKE2b-16 digest over (params, n_updates, last_update_ts_ns) for INV-15."""
    h = hashlib.blake2b(digest_size=16)
    h.update(n_updates.to_bytes(8, "little"))
    h.update(last_update_ts_ns.to_bytes(8, "little"))
    for p in params:
        h.update(repr(p).encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# State factory
# ---------------------------------------------------------------------------


def make_initial_state(
    n_params: int,
    *,
    init_value: float = 0.0,
) -> SelfLearningState:
    """Create a deterministic zero state.

    Args:
        n_params: Number of learnable parameters (must match feature dim).
        init_value: Initial value for every parameter.

    Returns:
        Fresh :class:`SelfLearningState`.
    """
    if n_params < 1:
        raise SelfLearningError(f"n_params must be >= 1, got {n_params}")
    params = tuple(float(init_value) for _ in range(n_params))
    digest = _compute_digest(params, 0, 0)
    return SelfLearningState(
        params=params,
        n_updates=0,
        last_update_ts_ns=0,
        win_rate=0.0,
        digest=digest,
    )


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def record_outcome(
    state: SelfLearningState,
    record: TradeOutcomeRecord,
    config: SelfLearningConfig,  # noqa: ARG001 — reserved for future validation hooks
) -> SelfLearningState:
    """Incorporate a new trade outcome into state.

    For this lane, incorporating a record only refreshes the digest
    so the ledger can verify the accumulation sequence.  The pending
    buffer is managed by the caller and passed into ``update()`` as an
    explicit sequence (pure-function contract).

    Args:
        state: Current lane state.
        record: New outcome to acknowledge.
        config: Lane configuration (reserved for future extension).

    Returns:
        Updated :class:`SelfLearningState` with refreshed digest.
    """
    new_digest = hashlib.blake2b(
        (state.digest + record.trade_id).encode(), digest_size=16
    ).hexdigest()
    return dataclasses.replace(state, digest=new_digest)


def should_update(
    state: SelfLearningState,
    pending_records: tuple[TradeOutcomeRecord, ...],
    config: SelfLearningConfig,
    current_ts_ns: int,
) -> bool:
    """Decide whether conditions are met to trigger a learning update.

    INV-15: deterministic — given identical arguments always returns the
    same boolean.

    Args:
        state: Current lane state.
        pending_records: Batch of unprocessed trade outcomes.
        config: Lane configuration.
        current_ts_ns: Current time (caller-supplied, no clock reads).

    Returns:
        ``True`` iff all update conditions are satisfied.
    """
    if len(pending_records) < config.min_trades_per_update:
        return False
    if (current_ts_ns - state.last_update_ts_ns) < config.update_cooldown_ns:
        return False
    wins = sum(1 for r in pending_records if r.pnl > 0.0)
    win_rate = wins / len(pending_records)
    return win_rate >= config.min_win_rate


def update(
    state: SelfLearningState,
    records: tuple[TradeOutcomeRecord, ...],
    config: SelfLearningConfig,
    current_ts_ns: int,
) -> tuple[SelfLearningState, list[LearningUpdate]]:
    """Run one self-supervised learning update over the pending records.

    Computes feature-weighted parameter updates from the mean PnL signal
    across the batch.  Win-trades have positive target; loss-trades have
    negative target.  Update rule:

        delta_i = learning_rate * mean(pnl_j * feature_j_i)   for all j

    where ``learning_rate = 0.01 / max(1, n_features)``.

    Args:
        state: Current lane state.
        records: Batch of outcome records.
        config: Lane configuration.
        current_ts_ns: Timestamp for the emitted ``LearningUpdate`` records.

    Returns:
        ``(new_state, list_of_updates)`` — the updates must pass governance
        approval before deployment (INV-12).
    """
    if not records:
        raise SelfLearningError("records must not be empty")

    n_params = len(state.params)
    if n_params == 0:
        return state, []

    wins = sum(1 for r in records if r.pnl > 0.0)
    win_rate = wins / len(records)

    # Compute gradient: mean PnL-weighted feature signal
    n = len(records)
    lr = 0.01 / max(1, n_params)
    grad = [0.0] * n_params
    for rec in records:
        nf = min(len(rec.features), n_params)
        for i in range(nf):
            grad[i] += rec.pnl * rec.features[i]
    grad = [g / n for g in grad]

    # Apply update
    new_params = tuple(state.params[i] + lr * grad[i] for i in range(n_params))
    new_updates = state.n_updates + 1
    digest = _compute_digest(new_params, new_updates, current_ts_ns)

    new_state = SelfLearningState(
        params=new_params,
        n_updates=new_updates,
        last_update_ts_ns=current_ts_ns,
        win_rate=win_rate,
        digest=digest,
    )

    strategy_id = records[0].strategy_id if records else ""
    learning_updates = build_learning_updates(new_state, strategy_id, current_ts_ns)
    return new_state, learning_updates


def build_learning_updates(
    state: SelfLearningState,
    strategy_id: str,
    ts_ns: int,
) -> list[LearningUpdate]:
    """Wrap state into ``LearningUpdate`` proposals for governance.

    One record is emitted per parameter that is non-zero, summarising the
    new value and the context of the update cycle.

    Args:
        state: Updated lane state after ``update()``.
        strategy_id: Strategy these parameters belong to.
        ts_ns: Timestamp for the proposals.

    Returns:
        List of :class:`LearningUpdate` records (one per non-zero param).
    """
    updates: list[LearningUpdate] = []
    for i, p in enumerate(state.params):
        if abs(p) < 1e-12:
            continue
        updates.append(
            LearningUpdate(
                ts_ns=ts_ns,
                strategy_id=strategy_id,
                parameter=f"self_learn_param_{i}",
                old_value="0.0",
                new_value=f"{p:.10f}",
                reason=f"self-supervised update cycle={state.n_updates}",
                meta={
                    "version": state.digest[:8],
                    "n_updates": str(state.n_updates),
                    "win_rate": f"{state.win_rate:.6f}",
                    "lane": SELF_LEARNING_VERSION,
                },
            )
        )
    return updates


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


__all__ = [
    "SELF_LEARNING_VERSION",
    "SelfLearningConfig",
    "SelfLearningError",
    "SelfLearningState",
    "TradeOutcomeRecord",
    "build_learning_updates",
    "make_initial_state",
    "record_outcome",
    "should_update",
    "update",
]
