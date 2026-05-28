# STATUS: RESEARCH_ONLY — not wired to production execution.
# ADAPTED FROM: MushroomRL/mushroom-rl
# (mushroom_rl/algorithms/actor_critic/deep_actor_critic/sac.py — SAC;
#  mushroom_rl/algorithms/actor_critic/deep_actor_critic/ppo.py — PPO;
#  mushroom_rl/core/core.py — Core training loop;
#  mushroom_rl/environments/environment.py — MDPInfo interface.)
"""C-41 — MushroomRL modular RL sandbox for flexible algorithm composition.

This module adapts the MushroomRL project
(https://github.com/MushroomRL/mushroom-rl, MIT License) as a flexible
algorithm composition toolkit for the evolution sandbox tier. Where
:mod:`evolution_engine.sandbox` provides the SB3/PPO-specific sandbox,
this module provides a framework-agnostic RL harness that supports:

* SAC (Soft Actor-Critic) — entropy-regularised off-policy
* PPO (Proximal Policy Optimisation) — clipped on-policy
* Any custom algorithm matching the :class:`RLAlgorithm` Protocol

DIX integration rules:

* OFFLINE_ONLY tier. No IO, no clock reads, no cross-engine imports.
* Deterministic seed forwarded to all components.
* Pure reducer: ``result = run_experiment(config, dynamics, seed)``.
* Output is a :class:`MushroomSandboxResult` record routed to
  governance via :class:`~core.contracts.learning.PatchProposal`.
* INV-15 byte-identical replays: same seed + config + dynamics →
  identical result.
* MushroomRL is NOT imported at module level — hidden behind a
  :class:`RLAlgorithm` Protocol seam. The module is importable
  on hosts without mushroom-rl installed.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import random
from collections.abc import Mapping, Sequence
from typing import Final, Protocol, runtime_checkable

from core.contracts.learning import PatchProposal

MUSHROOM_SANDBOX_VERSION: Final[str] = "c-41.v1"
"""Version tag carried on every result."""

DEFAULT_N_EPISODES: Final[int] = 100
"""Default number of training episodes."""

DEFAULT_N_STEPS_PER_EPISODE: Final[int] = 200
"""Default maximum steps per episode."""

DEFAULT_GAMMA: Final[float] = 0.99
"""Default discount factor."""

DEFAULT_LEARNING_RATE: Final[float] = 3e-4
"""Default learning rate for policy optimisation."""


# ---------------------------------------------------------------------------
# Protocol seam for RL algorithm (lazy import / testing)
# ---------------------------------------------------------------------------


@runtime_checkable
class RLAlgorithm(Protocol):
    """Protocol matching MushroomRL's algorithm interface.

    Implementations either wrap mushroom_rl.algorithms or provide
    deterministic fakes for testing.
    """

    def fit(self, dataset: Sequence[tuple[object, ...]]) -> None:
        """Train on a batch of (state, action, reward, next_state, done) tuples."""
        ...

    def draw_action(self, state: tuple[float, ...]) -> int:
        """Select action given current state."""
        ...


@runtime_checkable
class Environment(Protocol):
    """Protocol matching MushroomRL's MDPInfo-compatible environment."""

    def reset(self, seed: int | None = None) -> tuple[float, ...]:
        """Reset environment and return initial observation."""
        ...

    def step(self, action: int) -> tuple[tuple[float, ...], float, bool, Mapping[str, object]]:
        """Execute action, return (next_state, reward, done, info)."""
        ...


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MushroomSandboxError(ValueError):
    """Base class for typed errors raised by this module."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class MushroomSandboxConfig:
    """Immutable configuration for the MushroomRL sandbox.

    Attributes:
        algorithm_name: Algorithm identifier (e.g. "SAC", "PPO").
        n_episodes: Number of training episodes.
        n_steps_per_episode: Maximum steps per episode.
        gamma: Discount factor.
        learning_rate: Policy optimisation learning rate.
        seed: Deterministic seed for reproducibility.
        version: Algorithm version tag.
    """

    algorithm_name: str = "SAC"
    n_episodes: int = DEFAULT_N_EPISODES
    n_steps_per_episode: int = DEFAULT_N_STEPS_PER_EPISODE
    gamma: float = DEFAULT_GAMMA
    learning_rate: float = DEFAULT_LEARNING_RATE
    seed: int = 42
    version: str = MUSHROOM_SANDBOX_VERSION

    def __post_init__(self) -> None:
        if self.n_episodes < 1:
            raise MushroomSandboxError(f"n_episodes must be >= 1, got {self.n_episodes}")
        if self.n_steps_per_episode < 1:
            raise MushroomSandboxError(
                f"n_steps_per_episode must be >= 1, got {self.n_steps_per_episode}"
            )
        if not (0.0 < self.gamma <= 1.0):
            raise MushroomSandboxError(f"gamma must be in (0, 1], got {self.gamma}")
        if self.learning_rate <= 0.0:
            raise MushroomSandboxError(f"learning_rate must be > 0, got {self.learning_rate}")


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class EpisodeRecord:
    """Summary of a single training episode.

    Attributes:
        episode_idx: Zero-based episode index.
        total_reward: Cumulative reward for the episode.
        n_steps: Number of steps taken.
        terminated: Whether episode ended naturally (vs truncated).
    """

    episode_idx: int
    total_reward: float
    n_steps: int
    terminated: bool


@dataclasses.dataclass(frozen=True, slots=True)
class MushroomSandboxMetrics:
    """Aggregate training metrics.

    Attributes:
        mean_reward: Mean episode reward.
        best_reward: Best single-episode reward.
        worst_reward: Worst single-episode reward.
        total_steps: Total environment steps across all episodes.
        n_episodes: Number of episodes completed.
        convergence_episode: Episode at which best reward was first achieved.
    """

    mean_reward: float
    best_reward: float
    worst_reward: float
    total_steps: int
    n_episodes: int
    convergence_episode: int


@dataclasses.dataclass(frozen=True, slots=True)
class MushroomSandboxResult:
    """Full result of a sandbox training run.

    Attributes:
        config: Configuration used for the run.
        metrics: Aggregate training metrics.
        episode_records: Per-episode summaries.
        policy_weights: Final policy weights (flattened).
        digest: BLAKE2b digest for replay verification.
        proposal_id: Unique identifier for governance submission.
    """

    config: MushroomSandboxConfig
    metrics: MushroomSandboxMetrics
    episode_records: tuple[EpisodeRecord, ...]
    policy_weights: tuple[float, ...]
    digest: str
    proposal_id: str

    def to_payload(self) -> Mapping[str, object]:
        """Serialize to a plain dict for ledger storage."""
        return {
            "algorithm": self.config.algorithm_name,
            "seed": self.config.seed,
            "n_episodes": self.metrics.n_episodes,
            "mean_reward": self.metrics.mean_reward,
            "best_reward": self.metrics.best_reward,
            "total_steps": self.metrics.total_steps,
            "digest": self.digest,
            "proposal_id": self.proposal_id,
            "version": self.config.version,
        }


# ---------------------------------------------------------------------------
# Built-in deterministic environment (for testing + demonstration)
# ---------------------------------------------------------------------------


class SimpleLinearEnv:
    """Deterministic linear environment for testing.

    State is a 4-tuple of floats. Action is discrete (0 or 1).
    Reward is based on action alignment with state sign.
    """

    def __init__(self, n_states: int = 4) -> None:
        self._n_states = n_states
        self._rng: random.Random | None = None
        self._state: tuple[float, ...] = tuple(0.0 for _ in range(n_states))
        self._step_count = 0

    def reset(self, seed: int | None = None) -> tuple[float, ...]:
        self._rng = random.Random(seed)
        self._state = tuple(self._rng.gauss(0, 1) for _ in range(self._n_states))
        self._step_count = 0
        return self._state

    def step(self, action: int) -> tuple[tuple[float, ...], float, bool, Mapping[str, object]]:
        assert self._rng is not None
        self._step_count += 1
        state_sign = 1.0 if sum(self._state) > 0 else -1.0
        reward = 1.0 if (action == 1) == (state_sign > 0) else -0.5
        self._state = tuple(self._rng.gauss(0, 1) for _ in range(self._n_states))
        done = self._step_count >= 50
        return self._state, reward, done, {}


# ---------------------------------------------------------------------------
# Built-in tabular Q-learning algorithm (no external deps)
# ---------------------------------------------------------------------------


class TabularQLearner:
    """Simple tabular Q-learning that satisfies the RLAlgorithm Protocol.

    Used as default algorithm when MushroomRL is not installed.
    Discretises continuous states into bins for tabular lookup.
    """

    def __init__(
        self,
        n_actions: int = 2,
        n_bins: int = 5,
        learning_rate: float = 0.1,
        gamma: float = 0.99,
        epsilon: float = 0.1,
        seed: int = 42,
    ) -> None:
        self._n_actions = n_actions
        self._n_bins = n_bins
        self._lr = learning_rate
        self._gamma = gamma
        self._epsilon = epsilon
        self._rng = random.Random(seed)
        self._q: dict[tuple[int, ...], list[float]] = {}

    def _discretise(self, state: tuple[float, ...]) -> tuple[int, ...]:
        """Bin continuous state into discrete indices."""
        return tuple(
            min(self._n_bins - 1, max(0, int((s + 3.0) / 6.0 * self._n_bins))) for s in state
        )

    def _get_q(self, key: tuple[int, ...]) -> list[float]:
        if key not in self._q:
            self._q[key] = [0.0] * self._n_actions
        return self._q[key]

    def fit(self, dataset: Sequence[tuple[object, ...]]) -> None:
        """Train on a batch of (state, action, reward, next_state, done)."""
        for transition in dataset:
            state, action, reward, next_state, done = transition
            s_key = self._discretise(state)  # type: ignore[arg-type]
            ns_key = self._discretise(next_state)  # type: ignore[arg-type]
            q_s = self._get_q(s_key)
            q_ns = self._get_q(ns_key)
            target = float(reward) + (0.0 if done else self._gamma * max(q_ns))  # type: ignore[arg-type]
            q_s[int(action)] += self._lr * (target - q_s[int(action)])  # type: ignore[arg-type]

    def draw_action(self, state: tuple[float, ...]) -> int:
        """Epsilon-greedy action selection."""
        if self._rng.random() < self._epsilon:
            return self._rng.randint(0, self._n_actions - 1)
        s_key = self._discretise(state)
        q_values = self._get_q(s_key)
        return int(max(range(self._n_actions), key=lambda a: q_values[a]))

    def get_weights(self) -> tuple[float, ...]:
        """Flatten Q-table values for digest computation."""
        weights: list[float] = []
        for key in sorted(self._q.keys()):
            weights.extend(self._q[key])
        return tuple(weights)


# ---------------------------------------------------------------------------
# Core training loop (mirrors mushroom_rl/core/core.py)
# ---------------------------------------------------------------------------


def _compute_digest(weights: tuple[float, ...], config: MushroomSandboxConfig) -> str:
    """BLAKE2b digest over policy weights + config for INV-15."""
    h = hashlib.blake2b(digest_size=16)
    h.update(config.algorithm_name.encode())
    h.update(config.seed.to_bytes(8, "little"))
    h.update(config.n_episodes.to_bytes(4, "little"))
    for w in weights:
        h.update(w.hex().encode())
    return h.hexdigest()


def run_experiment(
    config: MushroomSandboxConfig,
    env: Environment | None = None,
    algorithm: RLAlgorithm | None = None,
    *,
    proposal_id: str = "",
) -> MushroomSandboxResult:
    """Run a complete RL training experiment.

    This is the main entry point mirroring MushroomRL's Core.learn() loop.
    Trains the algorithm on the environment for the configured number of
    episodes and returns a governance-ready result.

    Args:
        config: Sandbox configuration.
        env: Environment (defaults to SimpleLinearEnv if None).
        algorithm: RL algorithm (defaults to TabularQLearner if None).
        proposal_id: Unique ID for governance proposal tracking.

    Returns:
        ``MushroomSandboxResult`` with metrics and policy weights.
    """
    if not proposal_id:
        proposal_id = f"mushroom-{config.algorithm_name}-{config.seed}"

    if env is None:
        env = SimpleLinearEnv()
    if algorithm is None:
        algorithm = TabularQLearner(
            learning_rate=config.learning_rate,
            gamma=config.gamma,
            seed=config.seed,
        )

    episode_records: list[EpisodeRecord] = []
    total_steps = 0
    best_reward = -math.inf
    best_episode = 0

    for ep_idx in range(config.n_episodes):
        state = env.reset(seed=config.seed + ep_idx)
        episode_reward = 0.0
        ep_steps = 0
        terminated = False
        transitions: list[tuple[object, ...]] = []

        for _ in range(config.n_steps_per_episode):
            action = algorithm.draw_action(state)
            next_state, reward, done, _info = env.step(action)
            transitions.append((state, action, reward, next_state, done))
            episode_reward += reward
            ep_steps += 1
            state = next_state
            if done:
                terminated = True
                break

        # Fit algorithm on collected transitions
        algorithm.fit(transitions)
        total_steps += ep_steps

        if episode_reward > best_reward:
            best_reward = episode_reward
            best_episode = ep_idx

        episode_records.append(
            EpisodeRecord(
                episode_idx=ep_idx,
                total_reward=episode_reward,
                n_steps=ep_steps,
                terminated=terminated,
            )
        )

    # Compute metrics
    rewards = [r.total_reward for r in episode_records]
    mean_reward = sum(rewards) / len(rewards) if rewards else 0.0
    worst_reward = min(rewards) if rewards else 0.0

    metrics = MushroomSandboxMetrics(
        mean_reward=mean_reward,
        best_reward=best_reward,
        worst_reward=worst_reward,
        total_steps=total_steps,
        n_episodes=len(episode_records),
        convergence_episode=best_episode,
    )

    # Get policy weights for digest
    policy_weights: tuple[float, ...]
    if hasattr(algorithm, "get_weights"):
        policy_weights = algorithm.get_weights()  # type: ignore[union-attr]
    else:
        policy_weights = ()

    digest = _compute_digest(policy_weights, config)

    return MushroomSandboxResult(
        config=config,
        metrics=metrics,
        episode_records=tuple(episode_records),
        policy_weights=policy_weights,
        digest=digest,
        proposal_id=proposal_id,
    )


# ---------------------------------------------------------------------------
# Governance bridge
# ---------------------------------------------------------------------------


def build_patch_proposal(
    result: MushroomSandboxResult,
    target_strategy: str,
    ts_ns: int,
) -> PatchProposal:
    """Wrap sandbox result into a PatchProposal for governance.

    Args:
        result: Completed sandbox experiment result.
        target_strategy: Strategy ID the trained policy targets.
        ts_ns: Nanosecond timestamp for the proposal.

    Returns:
        ``PatchProposal`` record for governance approval queue.
    """
    return PatchProposal(
        ts_ns=ts_ns,
        patch_id=result.proposal_id,
        source=f"mushroom-rl/{result.config.algorithm_name}",
        target_strategy=target_strategy,
        touchpoints=("policy_weights", "algorithm_config"),
        rationale=(
            f"MushroomRL {result.config.algorithm_name} training: "
            f"mean_reward={result.metrics.mean_reward:.4f}, "
            f"best_reward={result.metrics.best_reward:.4f}, "
            f"episodes={result.metrics.n_episodes}"
        ),
        meta={
            "version": result.config.version,
            "digest": result.digest,
            "seed": str(result.config.seed),
        },
    )


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


__all__ = [
    "DEFAULT_GAMMA",
    "DEFAULT_LEARNING_RATE",
    "DEFAULT_N_EPISODES",
    "DEFAULT_N_STEPS_PER_EPISODE",
    "Environment",
    "EpisodeRecord",
    "MUSHROOM_SANDBOX_VERSION",
    "MushroomSandboxConfig",
    "MushroomSandboxError",
    "MushroomSandboxMetrics",
    "MushroomSandboxResult",
    "RLAlgorithm",
    "SimpleLinearEnv",
    "TabularQLearner",
    "build_patch_proposal",
    "run_experiment",
]
