# ADAPTED FROM: avalanche/training/supervised/ewc.py + avalanche/training/supervised/lwf.py
"""C-40 — Continual Learning lane (Elastic Weight Consolidation).

This module adapts the Elastic Weight Consolidation (EWC) algorithm from
the `avalanche` project (https://github.com/ContinualAI/avalanche,
MIT License) into an OFFLINE-tier learning lane behind the DIX
``LearningUpdate`` contract.

EWC solves catastrophic forgetting: when a model trained on Regime-A is
subsequently trained on Regime-B, naive SGD causes the model to forget
Regime-A. EWC adds a penalty to the loss function proportional to the
Fisher Information of each parameter with respect to previous tasks:

.. math::

    \\mathcal{L}_{\\text{EWC}} = \\mathcal{L}_{\\text{task}}
    + \\frac{\\lambda}{2} \\sum_{i} F_i (\\theta_i - \\theta^*_i)^2

where :math:`F_i` is the diagonal of the empirical Fisher Information
Matrix at the optimal parameters :math:`\\theta^*_i` for the previous
task.

DIX integration rules:

* OFFLINE-tier only — never on the hot path. Pure reducer pattern:
  ``state' = train_step(state, batch, config)``.
* No external imports of avalanche at runtime — the EWC math is
  reproduced in pure Python + numpy-style arithmetic via Protocol seam.
* Fisher Information is computed per-parameter from the squared gradient
  of the negative log-likelihood on a task's held-out data.
* New regime data → ``train()`` → governance approval before deployment.
* ``ewc_lambda=0.4`` default (per canonical spec).
* INV-15 (replay determinism): same data + same seed + same config →
  byte-identical state. Tests pin this.
* Proposed parameter mutations emitted as ``LearningUpdate`` records
  routed through governance approval queue (INV-12).
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Mapping, Sequence
from typing import Final, Protocol, runtime_checkable

from core.contracts.learning import LearningUpdate

CONTINUAL_LEARNER_VERSION: Final[str] = "c-40.v1"
"""Version tag carried on every state and proposed update."""

DEFAULT_EWC_LAMBDA: Final[float] = 0.4
"""Default EWC regularisation strength (canonical spec)."""

DEFAULT_LEARNING_RATE: Final[float] = 0.01
"""Default SGD step size for parameter updates."""

DEFAULT_MAX_TASKS: Final[int] = 64
"""Maximum number of retained task anchors (FIFO eviction)."""

DEFAULT_FISHER_SAMPLES: Final[int] = 256
"""Samples used to estimate diagonal Fisher Information."""


# ---------------------------------------------------------------------------
# Protocol seam for numeric backend (lazy import / testing)
# ---------------------------------------------------------------------------


@runtime_checkable
class ArrayLike(Protocol):
    """Minimal array protocol for numeric vectors."""

    def __len__(self) -> int: ...
    def __getitem__(self, idx: int) -> float: ...


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ContinualLearnerError(ValueError):
    """Base class for typed errors raised by this lane."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class ContinualLearnerConfig:
    """Immutable configuration for the EWC continual learner.

    Attributes:
        ewc_lambda: Regularisation strength (higher = more memory of old tasks).
        learning_rate: SGD step size for task-local gradient descent.
        max_tasks: Maximum retained task anchors before FIFO eviction.
        fisher_samples: Samples used for Fisher Information estimation.
        version: Algorithm version tag.
    """

    ewc_lambda: float = DEFAULT_EWC_LAMBDA
    learning_rate: float = DEFAULT_LEARNING_RATE
    max_tasks: int = DEFAULT_MAX_TASKS
    fisher_samples: int = DEFAULT_FISHER_SAMPLES
    version: str = CONTINUAL_LEARNER_VERSION

    def __post_init__(self) -> None:
        if self.ewc_lambda < 0.0:
            raise ContinualLearnerError(f"ewc_lambda must be >= 0, got {self.ewc_lambda}")
        if self.learning_rate <= 0.0:
            raise ContinualLearnerError(f"learning_rate must be > 0, got {self.learning_rate}")
        if self.max_tasks < 1:
            raise ContinualLearnerError(f"max_tasks must be >= 1, got {self.max_tasks}")
        if self.fisher_samples < 1:
            raise ContinualLearnerError(f"fisher_samples must be >= 1, got {self.fisher_samples}")


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class TaskAnchor:
    """Snapshot of optimal parameters + Fisher diagonal for a past task.

    Attributes:
        task_id: Unique identifier for the regime/task.
        optimal_params: Parameter values at task optimum.
        fisher_diagonal: Diagonal of empirical Fisher Information Matrix.
    """

    task_id: str
    optimal_params: tuple[float, ...]
    fisher_diagonal: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.optimal_params) != len(self.fisher_diagonal):
            raise ContinualLearnerError(
                f"optimal_params length ({len(self.optimal_params)}) "
                f"!= fisher_diagonal length ({len(self.fisher_diagonal)})"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class TrainingSample:
    """One training observation (feature vector + scalar loss/label).

    Attributes:
        ts_ns: Nanosecond timestamp of the observation.
        features: Feature vector as tuple of floats.
        label: Scalar target / reward signal.
        strategy_id: Associated strategy identifier.
    """

    ts_ns: int
    features: tuple[float, ...]
    label: float
    strategy_id: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class ContinualLearnerState:
    """Full serializable state of the EWC continual learner.

    Attributes:
        params: Current parameter vector.
        task_anchors: Retained task anchors (oldest first).
        n_tasks_seen: Total number of tasks trained on (including evicted).
        n_steps: Total training steps taken.
        version: Algorithm version at time of state creation.
        digest: BLAKE2b digest of the state for replay verification.
    """

    params: tuple[float, ...]
    task_anchors: tuple[TaskAnchor, ...]
    n_tasks_seen: int
    n_steps: int
    version: str
    digest: str

    def to_payload(self) -> Mapping[str, object]:
        """Serialize to a plain dict for ledger storage."""
        return {
            "params": list(self.params),
            "task_anchors": [
                {
                    "task_id": a.task_id,
                    "optimal_params": list(a.optimal_params),
                    "fisher_diagonal": list(a.fisher_diagonal),
                }
                for a in self.task_anchors
            ],
            "n_tasks_seen": self.n_tasks_seen,
            "n_steps": self.n_steps,
            "version": self.version,
            "digest": self.digest,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class TrainOutcome:
    """Result of a training episode on a single task.

    Attributes:
        state: Updated learner state after training.
        final_loss: Loss value at end of training.
        ewc_penalty: EWC regularisation penalty at end of training.
        n_steps_taken: Number of gradient steps performed.
        task_id: Task identifier that was trained.
    """

    state: ContinualLearnerState
    final_loss: float
    ewc_penalty: float
    n_steps_taken: int
    task_id: str


# ---------------------------------------------------------------------------
# State factory
# ---------------------------------------------------------------------------


def _compute_digest(params: tuple[float, ...], n_steps: int) -> str:
    """BLAKE2b digest over params + step count for INV-15."""
    h = hashlib.blake2b(digest_size=16)
    h.update(n_steps.to_bytes(8, "little"))
    for p in params:
        h.update(p.hex().encode())
    return h.hexdigest()


def make_initial_state(
    n_params: int,
    *,
    init_value: float = 0.0,
    version: str = CONTINUAL_LEARNER_VERSION,
) -> ContinualLearnerState:
    """Create a deterministic zero-state with ``n_params`` parameters.

    Args:
        n_params: Number of learnable parameters.
        init_value: Initial value for all parameters.
        version: Algorithm version tag.

    Returns:
        A fresh ``ContinualLearnerState`` ready for training.
    """
    if n_params < 1:
        raise ContinualLearnerError(f"n_params must be >= 1, got {n_params}")
    params = tuple(init_value for _ in range(n_params))
    digest = _compute_digest(params, 0)
    return ContinualLearnerState(
        params=params,
        task_anchors=(),
        n_tasks_seen=0,
        n_steps=0,
        version=version,
        digest=digest,
    )


# ---------------------------------------------------------------------------
# EWC core math
# ---------------------------------------------------------------------------


def _ewc_penalty(
    params: tuple[float, ...],
    anchors: tuple[TaskAnchor, ...],
    ewc_lambda: float,
) -> float:
    """Compute EWC penalty: (lambda/2) * sum_tasks sum_i F_i*(theta_i - theta*_i)^2."""
    if not anchors:
        return 0.0
    penalty = 0.0
    for anchor in anchors:
        for p, p_star, f_i in zip(
            params, anchor.optimal_params, anchor.fisher_diagonal, strict=False
        ):
            penalty += f_i * (p - p_star) ** 2
    return (ewc_lambda / 2.0) * penalty


def _ewc_penalty_grad(
    params: tuple[float, ...],
    anchors: tuple[TaskAnchor, ...],
    ewc_lambda: float,
) -> tuple[float, ...]:
    """Gradient of EWC penalty w.r.t. params."""
    n = len(params)
    grad = [0.0] * n
    for anchor in anchors:
        for i in range(n):
            grad[i] += (
                ewc_lambda * anchor.fisher_diagonal[i] * (params[i] - anchor.optimal_params[i])
            )
    return tuple(grad)


def _task_loss(
    params: tuple[float, ...],
    sample: TrainingSample,
) -> float:
    """Simple linear model MSE loss for one sample: 0.5*(y - w.x)^2."""
    n = min(len(params), len(sample.features))
    pred = sum(params[i] * sample.features[i] for i in range(n))
    return 0.5 * (sample.label - pred) ** 2


def _task_loss_grad(
    params: tuple[float, ...],
    sample: TrainingSample,
) -> tuple[float, ...]:
    """Gradient of MSE loss w.r.t. params for one sample."""
    n = len(params)
    nf = len(sample.features)
    pred = sum(params[i] * sample.features[i] for i in range(min(n, nf)))
    residual = pred - sample.label
    grad = []
    for i in range(n):
        if i < nf:
            grad.append(residual * sample.features[i])
        else:
            grad.append(0.0)
    return tuple(grad)


def _estimate_fisher(
    params: tuple[float, ...],
    samples: Sequence[TrainingSample],
    max_samples: int,
) -> tuple[float, ...]:
    """Estimate diagonal Fisher Information from squared gradients.

    Fisher_i = (1/N) * sum_n (d log p / d theta_i)^2
    For MSE loss, this is the mean of squared per-sample gradients.
    """
    n = len(params)
    fisher = [0.0] * n
    use_samples = samples[:max_samples]
    if not use_samples:
        return tuple(fisher)
    for sample in use_samples:
        grad = _task_loss_grad(params, sample)
        for i in range(n):
            fisher[i] += grad[i] ** 2
    count = len(use_samples)
    return tuple(f / count for f in fisher)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def train(
    state: ContinualLearnerState,
    task_id: str,
    samples: Sequence[TrainingSample],
    config: ContinualLearnerConfig,
    *,
    max_epochs: int = 10,
    convergence_tol: float = 1e-6,
) -> TrainOutcome:
    """Train on a new task using EWC-regularised gradient descent.

    After training, the current parameters are anchored as optimal for
    this task with their estimated Fisher Information diagonal.

    Args:
        state: Current learner state.
        task_id: Unique identifier for this regime/task.
        samples: Training observations for this task.
        config: EWC configuration.
        max_epochs: Maximum passes over the data.
        convergence_tol: Stop if loss improvement < tol.

    Returns:
        ``TrainOutcome`` with updated state and training statistics.
    """
    if not samples:
        raise ContinualLearnerError("samples must not be empty")
    if not task_id:
        raise ContinualLearnerError("task_id must not be empty")

    params = list(state.params)
    n = len(params)
    anchors = state.task_anchors
    n_steps = state.n_steps
    prev_total_loss = float("inf")
    steps_taken = 0

    for _epoch in range(max_epochs):
        for sample in samples:
            # Task loss gradient
            task_grad = _task_loss_grad(tuple(params), sample)
            # EWC penalty gradient
            ewc_grad = _ewc_penalty_grad(tuple(params), anchors, config.ewc_lambda)
            # Combined gradient descent step
            for i in range(n):
                params[i] -= config.learning_rate * (task_grad[i] + ewc_grad[i])
            n_steps += 1
            steps_taken += 1

        # Check convergence
        total_loss = sum(_task_loss(tuple(params), s) for s in samples) / len(samples)
        ewc_pen = _ewc_penalty(tuple(params), anchors, config.ewc_lambda)
        combined = total_loss + ewc_pen
        if abs(prev_total_loss - combined) < convergence_tol:
            break
        prev_total_loss = combined

    # Estimate Fisher Information for this task
    final_params = tuple(params)
    fisher = _estimate_fisher(final_params, samples, config.fisher_samples)

    # Create anchor for this task
    new_anchor = TaskAnchor(
        task_id=task_id,
        optimal_params=final_params,
        fisher_diagonal=fisher,
    )

    # FIFO eviction of oldest anchors if at capacity
    existing = list(anchors)
    existing.append(new_anchor)
    if len(existing) > config.max_tasks:
        existing = existing[-config.max_tasks :]
    new_anchors = tuple(existing)

    final_loss = sum(_task_loss(final_params, s) for s in samples) / len(samples)
    final_ewc = _ewc_penalty(final_params, new_anchors, config.ewc_lambda)
    digest = _compute_digest(final_params, n_steps)

    new_state = ContinualLearnerState(
        params=final_params,
        task_anchors=new_anchors,
        n_tasks_seen=state.n_tasks_seen + 1,
        n_steps=n_steps,
        version=config.version,
        digest=digest,
    )

    return TrainOutcome(
        state=new_state,
        final_loss=final_loss,
        ewc_penalty=final_ewc,
        n_steps_taken=steps_taken,
        task_id=task_id,
    )


# ---------------------------------------------------------------------------
# Governance bridge
# ---------------------------------------------------------------------------


def build_learning_update(
    outcome: TrainOutcome,
    strategy_id: str,
    ts_ns: int,
    *,
    param_names: Sequence[str] | None = None,
    old_params: tuple[float, ...] | None = None,
) -> list[LearningUpdate]:
    """Wrap training outcome into LearningUpdate proposals for governance.

    Each parameter that changed produces one ``LearningUpdate`` record.
    These must pass governance approval before deployment (INV-12).

    Args:
        outcome: Result of ``train()``.
        strategy_id: Strategy these parameters belong to.
        ts_ns: Nanosecond timestamp for the proposal.
        param_names: Optional human-readable names for parameters.
        old_params: Previous parameter values (for delta reporting).

    Returns:
        List of ``LearningUpdate`` records (one per changed parameter).
    """
    updates: list[LearningUpdate] = []
    new_params = outcome.state.params
    n = len(new_params)

    if old_params is None:
        old_params = tuple(0.0 for _ in range(n))

    for i in range(n):
        if abs(new_params[i] - old_params[i]) < 1e-12:
            continue
        name = param_names[i] if param_names and i < len(param_names) else f"param_{i}"
        updates.append(
            LearningUpdate(
                ts_ns=ts_ns,
                strategy_id=strategy_id,
                parameter=name,
                old_value=f"{old_params[i]:.10f}",
                new_value=f"{new_params[i]:.10f}",
                reason=f"EWC continual learning task={outcome.task_id}",
                meta={
                    "version": outcome.state.version,
                    "task_id": outcome.task_id,
                    "final_loss": f"{outcome.final_loss:.8f}",
                    "ewc_penalty": f"{outcome.ewc_penalty:.8f}",
                },
            )
        )
    return updates


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------


def evaluate_forgetting(
    state: ContinualLearnerState,
    task_samples: Mapping[str, Sequence[TrainingSample]],
) -> Mapping[str, float]:
    """Evaluate per-task loss to measure forgetting.

    Args:
        state: Current learner state.
        task_samples: Mapping of task_id → held-out samples.

    Returns:
        Mapping of task_id → mean loss on that task.
    """
    results: dict[str, float] = {}
    for task_id, samples in task_samples.items():
        if not samples:
            continue
        total = sum(_task_loss(state.params, s) for s in samples)
        results[task_id] = total / len(samples)
    return results


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


__all__ = [
    "CONTINUAL_LEARNER_VERSION",
    "ContinualLearnerConfig",
    "ContinualLearnerError",
    "ContinualLearnerState",
    "DEFAULT_EWC_LAMBDA",
    "DEFAULT_FISHER_SAMPLES",
    "DEFAULT_LEARNING_RATE",
    "DEFAULT_MAX_TASKS",
    "TaskAnchor",
    "TrainOutcome",
    "TrainingSample",
    "build_learning_update",
    "evaluate_forgetting",
    "make_initial_state",
    "train",
]
