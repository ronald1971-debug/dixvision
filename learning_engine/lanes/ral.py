"""Retrospective Action Learning (RAL) lane.

Learns from past trading decisions by replaying historical decision points
and comparing the chosen action against counterfactual alternatives.  Regret
signal drives parameter updates: high regret means the strategy frequently
chose sub-optimal actions and should up-weight features that predict the
counterfactual outcome.

DIX integration rules:
* OFFLINE-tier only — pure reducer, no clock reads, no IO.
* INV-15: identical inputs → identical outputs. Digest pinned by tests.
* INV-12: ``build_learning_updates`` emits proposals; governance approves.
* No cross-engine imports beyond ``core.contracts.learning``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from typing import Final

from core.contracts.learning import LearningUpdate

RAL_VERSION: Final[str] = "ral.v1"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RALError(ValueError):
    """Base error for the RAL lane."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class RALConfig:
    """Immutable configuration for the Retrospective Action Learning lane.

    Attributes:
        replay_window: Maximum number of :class:`DecisionReplay` records to
            retain for mean-regret computation.
        counterfactual_temperature: Softmax temperature applied to
            counterfactual rewards when weighting the regret signal.
            Lower values make the algorithm greedier toward the best
            counterfactual; higher values average more uniformly.
        version: Algorithm version tag.
    """

    replay_window: int = 200
    counterfactual_temperature: float = 0.5
    version: str = RAL_VERSION

    def __post_init__(self) -> None:
        if self.replay_window < 1:
            raise RALError(f"replay_window must be >= 1, got {self.replay_window}")
        if self.counterfactual_temperature <= 0.0 or not math.isfinite(
            self.counterfactual_temperature
        ):
            raise RALError(
                f"counterfactual_temperature must be finite and > 0, "
                f"got {self.counterfactual_temperature}"
            )


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class DecisionReplay:
    """One historical decision point with counterfactual outcomes.

    Attributes:
        ts_ns: Nanosecond timestamp of the original decision.
        trade_id: Unique trade identifier.
        chosen_action: The action the strategy actually took.
        counterfactual_actions: Tuple of alternative actions considered but
            not taken.
        actual_reward: Realised reward from the chosen action.
        counterfactual_rewards: Realised (or estimated) rewards for each
            alternative action, in the same order as
            ``counterfactual_actions``.
    """

    ts_ns: int
    trade_id: str
    chosen_action: str
    counterfactual_actions: tuple[str, ...]
    actual_reward: float
    counterfactual_rewards: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.ts_ns <= 0:
            raise RALError(f"ts_ns must be positive, got {self.ts_ns}")
        if not self.trade_id:
            raise RALError("trade_id must be non-empty")
        if not self.chosen_action:
            raise RALError("chosen_action must be non-empty")
        if len(self.counterfactual_actions) != len(self.counterfactual_rewards):
            raise RALError(
                f"counterfactual_actions length ({len(self.counterfactual_actions)}) "
                f"!= counterfactual_rewards length ({len(self.counterfactual_rewards)})"
            )
        if not math.isfinite(self.actual_reward):
            raise RALError(f"actual_reward must be finite, got {self.actual_reward}")
        for i, r in enumerate(self.counterfactual_rewards):
            if not math.isfinite(r):
                raise RALError(
                    f"counterfactual_rewards[{i}] must be finite, got {r}"
                )


@dataclasses.dataclass(frozen=True, slots=True)
class RALState:
    """Fully serializable state for the RAL lane.

    Attributes:
        params: Current parameter vector (action-feature weights).
        mean_regret: Exponentially smoothed mean regret across replayed
            decisions.
        n_replays: Total number of :class:`DecisionReplay` records
            consumed.
        digest: BLAKE2b digest for INV-15 replay verification.
    """

    params: tuple[float, ...]
    mean_regret: float
    n_replays: int
    digest: str

    def __post_init__(self) -> None:
        if self.n_replays < 0:
            raise RALError(f"n_replays must be >= 0, got {self.n_replays}")
        if not math.isfinite(self.mean_regret):
            raise RALError(f"mean_regret must be finite, got {self.mean_regret}")


# ---------------------------------------------------------------------------
# Digest helpers
# ---------------------------------------------------------------------------


def _compute_digest(
    params: tuple[float, ...], n_replays: int, mean_regret: float
) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update(n_replays.to_bytes(8, "little"))
    h.update(repr(mean_regret).encode())
    for p in params:
        h.update(repr(p).encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# State factory
# ---------------------------------------------------------------------------


def make_initial_state(n_params: int, *, init_value: float = 0.0) -> RALState:
    """Create a deterministic zero state.

    Args:
        n_params: Number of learnable parameters.
        init_value: Initial value for all parameters.

    Returns:
        Fresh :class:`RALState`.
    """
    if n_params < 1:
        raise RALError(f"n_params must be >= 1, got {n_params}")
    params = tuple(float(init_value) for _ in range(n_params))
    digest = _compute_digest(params, 0, 0.0)
    return RALState(params=params, mean_regret=0.0, n_replays=0, digest=digest)


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def compute_regret(replay: DecisionReplay) -> float:
    """Compute the regret for a single decision replay.

    Regret is defined as ``max(counterfactual_rewards) - actual_reward``.
    Zero counterfactuals → zero regret.

    INV-15: pure, deterministic.

    Args:
        replay: Historical decision with counterfactual outcomes.

    Returns:
        Non-negative regret value.  Clamped to ``>= 0`` so past lucky
        outcomes (outperforming all counterfactuals) do not produce
        negative regret.
    """
    if not replay.counterfactual_rewards:
        return 0.0
    max_cf = max(replay.counterfactual_rewards)
    return max(0.0, max_cf - replay.actual_reward)


def ral_update(
    state: RALState,
    replays: tuple[DecisionReplay, ...],
    config: RALConfig,
) -> RALState:
    """Apply a batch of decision replays to update the RAL state.

    Uses regret-weighted gradient descent: parameters are nudged toward
    features that distinguish high-regret decisions (where a better action
    was available) from low-regret decisions.

    The update rule is:

        regret_i = compute_regret(replay_i)
        delta_params += regret_i * sign(max_counterfactual_reward - actual_reward)
        mean_regret = EMA(regrets, alpha=0.1)

    INV-15: deterministic given identical ``(state, replays, config)``.

    Args:
        state: Current lane state.
        replays: Batch of :class:`DecisionReplay` records.
        config: RAL configuration.

    Returns:
        Updated :class:`RALState`.
    """
    if not replays:
        raise RALError("replays must not be empty")
    if len(replays) > config.replay_window:
        # Use the most recent replay_window records
        replays = replays[-config.replay_window :]

    n_params = len(state.params)
    lr = 0.01 / max(1, n_params)

    regrets: list[float] = []
    param_accum = list(state.params)

    for replay in replays:
        regret = compute_regret(replay)
        regrets.append(regret)

        # Scale update by regret and temperature
        if regret > 0.0 and replay.counterfactual_rewards:
            # Softmax over counterfactual rewards to weight the gradient
            temps = [
                r / config.counterfactual_temperature
                for r in replay.counterfactual_rewards
            ]
            max_t = max(temps)
            exps = [math.exp(t - max_t) for t in temps]
            total_exp = sum(exps)
            weights = [e / total_exp for e in exps]

            # Regret-weighted parameter nudge (uniform feature signal without
            # feature vector available at this level — nudge all params evenly)
            nudge = lr * regret * sum(
                w for w, r in zip(weights, replay.counterfactual_rewards) if r > replay.actual_reward
            )
            for i in range(n_params):
                param_accum[i] += nudge

    # EMA of mean regret
    ema_alpha = 0.1
    batch_mean_regret = (sum(regrets) / len(regrets)) if regrets else 0.0
    new_mean_regret = (
        ema_alpha * batch_mean_regret + (1.0 - ema_alpha) * state.mean_regret
    )

    new_params = tuple(param_accum)
    new_n_replays = state.n_replays + len(replays)
    new_digest = _compute_digest(new_params, new_n_replays, new_mean_regret)

    return RALState(
        params=new_params,
        mean_regret=new_mean_regret,
        n_replays=new_n_replays,
        digest=new_digest,
    )


def build_learning_updates(
    state: RALState,
    strategy_id: str,
    ts_ns: int,
) -> list[LearningUpdate]:
    """Wrap RAL state into ``LearningUpdate`` proposals for governance.

    One record per non-zero parameter.  The mean regret is surfaced in the
    ``meta`` field so governance can gate on signal quality.

    Args:
        state: Updated RAL state.
        strategy_id: Strategy these parameters belong to.
        ts_ns: Timestamp for the proposals.

    Returns:
        List of :class:`LearningUpdate` records.
    """
    updates: list[LearningUpdate] = []
    for i, p in enumerate(state.params):
        if abs(p) < 1e-12:
            continue
        updates.append(
            LearningUpdate(
                ts_ns=ts_ns,
                strategy_id=strategy_id,
                parameter=f"ral_param_{i}",
                old_value="0.0",
                new_value=f"{p:.10f}",
                reason=f"RAL retrospective update n_replays={state.n_replays}",
                meta={
                    "version": RAL_VERSION,
                    "mean_regret": f"{state.mean_regret:.8f}",
                    "n_replays": str(state.n_replays),
                    "digest": state.digest[:8],
                },
            )
        )
    return updates


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


__all__ = [
    "RAL_VERSION",
    "RALConfig",
    "RALError",
    "RALState",
    "DecisionReplay",
    "build_learning_updates",
    "compute_regret",
    "make_initial_state",
    "ral_update",
]
