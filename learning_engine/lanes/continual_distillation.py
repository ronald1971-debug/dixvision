"""Continual knowledge distillation lane.

Compresses a large teacher model's behaviour into a smaller student model
using soft cross-entropy loss (Hinton et al., 2015).  The lane runs in the
OFFLINE tier and emits ``LearningUpdate`` proposals — it never modifies a
live model directly.

Distillation loss:

    L = alpha * CE(student, hard_label) + (1 - alpha) * soft_CE(student, teacher, T)

where ``T`` is the temperature that softens the teacher's logit distribution
and ``alpha`` controls the trade-off between fitting hard labels and
mimicking soft teacher behaviour.

DIX integration rules:
* OFFLINE-tier only — pure functions, no IO, no clock reads.
* INV-15: same inputs → same outputs. Digest pinned by tests.
* INV-12: ``build_learning_updates`` emits proposals; governance approves.
* No external ML-framework imports; pure Python + stdlib math only.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from typing import Final

from core.contracts.learning import LearningUpdate

DISTILLATION_VERSION: Final[str] = "distill.v1"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DistillationError(ValueError):
    """Base error for the continual distillation lane."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class DistillationConfig:
    """Immutable configuration for the knowledge distillation lane.

    Attributes:
        temperature: Softens teacher logits before computing the soft
            cross-entropy.  Higher values produce a softer, more
            uniform distribution.
        alpha: Convex weight balancing hard-label CE (``alpha``) against
            soft distillation CE (``1 - alpha``).  ``0.0`` means pure
            distillation; ``1.0`` means pure hard-label training.
        learning_rate: SGD step size for the student parameter update.
        version: Algorithm version tag.
    """

    temperature: float = 3.0
    alpha: float = 0.5
    learning_rate: float = 0.01
    version: str = DISTILLATION_VERSION

    def __post_init__(self) -> None:
        if self.temperature <= 0.0 or not math.isfinite(self.temperature):
            raise DistillationError(
                f"temperature must be finite and > 0, got {self.temperature}"
            )
        if not (0.0 <= self.alpha <= 1.0):
            raise DistillationError(f"alpha must be in [0, 1], got {self.alpha}")
        if self.learning_rate <= 0.0 or not math.isfinite(self.learning_rate):
            raise DistillationError(
                f"learning_rate must be finite and > 0, got {self.learning_rate}"
            )


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class DistillationSample:
    """One training sample for distillation.

    Attributes:
        ts_ns: Nanosecond timestamp of the sample.
        features: Feature vector (student model input).
        hard_label: Ground-truth class label (integer index).
        teacher_logits: Raw logit scores from the teacher model, one per
            class.  These are softened by ``temperature`` to form the
            soft targets.
    """

    ts_ns: int
    features: tuple[float, ...]
    hard_label: int
    teacher_logits: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.ts_ns <= 0:
            raise DistillationError(f"ts_ns must be positive, got {self.ts_ns}")
        if not self.features:
            raise DistillationError("features must be non-empty")
        for i, f in enumerate(self.features):
            if not math.isfinite(f):
                raise DistillationError(f"features[{i}] must be finite, got {f}")
        if self.hard_label < 0:
            raise DistillationError(f"hard_label must be >= 0, got {self.hard_label}")
        if not self.teacher_logits:
            raise DistillationError("teacher_logits must be non-empty")
        for i, t in enumerate(self.teacher_logits):
            if not math.isfinite(t):
                raise DistillationError(f"teacher_logits[{i}] must be finite, got {t}")
        n_classes = len(self.teacher_logits)
        if self.hard_label >= n_classes:
            raise DistillationError(
                f"hard_label {self.hard_label} out of range for {n_classes} classes"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class DistillationState:
    """Fully serializable state of the student model.

    Attributes:
        student_params: Current student parameter vector.
        n_steps: Total number of distillation steps completed.
        final_loss: Distillation loss at the last completed step.
        digest: BLAKE2b digest for INV-15 replay verification.
    """

    student_params: tuple[float, ...]
    n_steps: int
    final_loss: float
    digest: str

    def __post_init__(self) -> None:
        if self.n_steps < 0:
            raise DistillationError(f"n_steps must be >= 0, got {self.n_steps}")
        if not math.isfinite(self.final_loss):
            raise DistillationError(f"final_loss must be finite, got {self.final_loss}")


# ---------------------------------------------------------------------------
# Digest helpers
# ---------------------------------------------------------------------------


def _compute_digest(
    params: tuple[float, ...], n_steps: int, final_loss: float
) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update(n_steps.to_bytes(8, "little"))
    h.update(repr(final_loss).encode())
    for p in params:
        h.update(repr(p).encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# State factory
# ---------------------------------------------------------------------------


def make_initial_state(n_params: int, *, init_value: float = 0.0) -> DistillationState:
    """Create a deterministic zero student state.

    Args:
        n_params: Dimensionality of the student parameter vector.
        init_value: Initial value for all parameters.

    Returns:
        Fresh :class:`DistillationState`.
    """
    if n_params < 1:
        raise DistillationError(f"n_params must be >= 1, got {n_params}")
    params = tuple(float(init_value) for _ in range(n_params))
    digest = _compute_digest(params, 0, 0.0)
    return DistillationState(
        student_params=params, n_steps=0, final_loss=0.0, digest=digest
    )


# ---------------------------------------------------------------------------
# Pure math
# ---------------------------------------------------------------------------


def _softmax(logits: tuple[float, ...], temperature: float) -> tuple[float, ...]:
    """Numerically stable softmax with temperature scaling.

    Args:
        logits: Raw model scores.
        temperature: Scaling factor applied before exponentiation.

    Returns:
        Probability distribution summing to 1.0.
    """
    scaled = [x / temperature for x in logits]
    max_val = max(scaled)
    exps = [math.exp(s - max_val) for s in scaled]
    total = sum(exps)
    return tuple(e / total for e in exps)


def soft_cross_entropy(
    student_logits: tuple[float, ...],
    teacher_logits: tuple[float, ...],
    temperature: float,
) -> float:
    """Soft cross-entropy between student and softened teacher distributions.

    Computes:  -sum_c [ p_teacher(c|T) * log(p_student(c|T)) ]

    Both distributions are softened by the same ``temperature`` before the
    KL-style loss is applied, which is the Hinton et al. convention.  The
    result is scaled by ``temperature^2`` so the gradient magnitude is
    independent of ``temperature`` (standard distillation practice).

    INV-15: pure, deterministic.

    Args:
        student_logits: Student model raw scores (one per class).
        teacher_logits: Teacher model raw scores (one per class).
        temperature: Softmax temperature (> 0).

    Returns:
        Scalar soft cross-entropy loss value (>= 0).
    """
    if len(student_logits) != len(teacher_logits):
        raise DistillationError(
            f"student_logits length ({len(student_logits)}) "
            f"!= teacher_logits length ({len(teacher_logits)})"
        )
    if not student_logits:
        raise DistillationError("logits must be non-empty")
    if temperature <= 0.0:
        raise DistillationError(f"temperature must be > 0, got {temperature}")

    p_teacher = _softmax(teacher_logits, temperature)
    p_student = _softmax(student_logits, temperature)
    # Cross-entropy: -sum(p_t * log(p_s))
    ce = -sum(
        pt * math.log(max(ps, 1e-12))
        for pt, ps in zip(p_teacher, p_student, strict=True)
    )
    # Scale by T^2 to preserve gradient magnitude
    return ce * (temperature ** 2)


def _hard_cross_entropy(
    student_logits: tuple[float, ...], hard_label: int
) -> float:
    """Standard cross-entropy against a one-hot hard label.

    Args:
        student_logits: Student model raw scores.
        hard_label: Integer class index (the true label).

    Returns:
        Scalar cross-entropy loss.
    """
    p_student = _softmax(student_logits, temperature=1.0)
    prob_correct = max(p_student[hard_label], 1e-12)
    return -math.log(prob_correct)


def distillation_loss(
    student_logits: tuple[float, ...],
    hard_label: int,
    teacher_logits: tuple[float, ...],
    config: DistillationConfig,
) -> float:
    """Combined distillation loss: alpha * hard_CE + (1-alpha) * soft_CE.

    INV-15: pure, deterministic.

    Args:
        student_logits: Student model raw scores.
        hard_label: Ground-truth integer class index.
        teacher_logits: Teacher model raw scores.
        config: Distillation configuration.

    Returns:
        Combined scalar loss value.
    """
    hard_ce = _hard_cross_entropy(student_logits, hard_label)
    soft_ce = soft_cross_entropy(student_logits, teacher_logits, config.temperature)
    return config.alpha * hard_ce + (1.0 - config.alpha) * soft_ce


def distillation_step(
    student_params: tuple[float, ...],
    sample: DistillationSample,
    config: DistillationConfig,
) -> tuple[tuple[float, ...], float]:
    """Apply one gradient-descent distillation step.

    Uses a linear student model (dot product of params and features) to
    produce logits.  The gradient of the combined distillation loss w.r.t.
    each parameter is approximated by finite differences scaled against the
    feature vector.

    INV-15: pure, deterministic.

    Args:
        student_params: Current student parameter vector.
        sample: One :class:`DistillationSample`.
        config: Distillation configuration.

    Returns:
        ``(new_params, loss)`` — updated params and scalar loss at this step.
    """
    n_params = len(student_params)
    n_features = len(sample.features)
    n_classes = len(sample.teacher_logits)

    if n_params == 0 or n_classes == 0:
        return student_params, 0.0

    # Partition params into n_classes * n_features weight matrix (row-major)
    # or fall back to a single shared weight vector when under-parameterised.
    params_per_class = max(1, n_params // n_classes)
    student_logits_list: list[float] = []
    for c in range(n_classes):
        offset = (c * params_per_class) % n_params
        score = 0.0
        for j in range(min(params_per_class, n_features)):
            idx = (offset + j) % n_params
            fj = sample.features[j] if j < n_features else 0.0
            score += student_params[idx] * fj
        student_logits_list.append(score)
    student_logits = tuple(student_logits_list)

    loss = distillation_loss(student_logits, sample.hard_label, sample.teacher_logits, config)

    # Compute analytic gradient: dL/dw_i = dL/dlogit_c * feature_j
    # Simplified: use soft targets minus hard one-hot as the error signal
    p_student = _softmax(student_logits, temperature=1.0)
    p_teacher = _softmax(sample.teacher_logits, config.temperature)

    # One-hot for hard label
    one_hot = [1.0 if c == sample.hard_label else 0.0 for c in range(n_classes)]

    # Combined gradient at logit level:
    # alpha * (p_student - one_hot) + (1-alpha) * (p_student_T - p_teacher_T)
    p_student_T = _softmax(student_logits, config.temperature)
    logit_grad = [
        config.alpha * (p_student[c] - one_hot[c])
        + (1.0 - config.alpha) * (p_student_T[c] - p_teacher[c])
        for c in range(n_classes)
    ]

    # Back-prop to params
    param_grad = [0.0] * n_params
    for c in range(n_classes):
        offset = (c * params_per_class) % n_params
        for j in range(min(params_per_class, n_features)):
            idx = (offset + j) % n_params
            fj = sample.features[j] if j < n_features else 0.0
            param_grad[idx] += logit_grad[c] * fj

    new_params = tuple(
        student_params[i] - config.learning_rate * param_grad[i]
        for i in range(n_params)
    )
    return new_params, loss


# ---------------------------------------------------------------------------
# Multi-sample training
# ---------------------------------------------------------------------------


def train(
    state: DistillationState,
    samples: tuple[DistillationSample, ...],
    config: DistillationConfig,
) -> DistillationState:
    """Run distillation over a batch of samples.

    Args:
        state: Current student state.
        samples: Batch of :class:`DistillationSample` records.
        config: Distillation configuration.

    Returns:
        Updated :class:`DistillationState`.
    """
    if not samples:
        raise DistillationError("samples must not be empty")

    params = state.student_params
    final_loss = 0.0
    for sample in samples:
        params, final_loss = distillation_step(params, sample, config)

    n_steps = state.n_steps + len(samples)
    digest = _compute_digest(params, n_steps, final_loss)
    return DistillationState(
        student_params=params,
        n_steps=n_steps,
        final_loss=final_loss,
        digest=digest,
    )


# ---------------------------------------------------------------------------
# Governance bridge
# ---------------------------------------------------------------------------


def build_learning_updates(
    state: DistillationState,
    strategy_id: str,
    ts_ns: int,
) -> list[LearningUpdate]:
    """Wrap distillation state into ``LearningUpdate`` proposals for governance.

    One record per non-zero student parameter.

    Args:
        state: Updated distillation state.
        strategy_id: Strategy these parameters belong to.
        ts_ns: Timestamp for the proposals.

    Returns:
        List of :class:`LearningUpdate` records.
    """
    updates: list[LearningUpdate] = []
    for i, p in enumerate(state.student_params):
        if abs(p) < 1e-12:
            continue
        updates.append(
            LearningUpdate(
                ts_ns=ts_ns,
                strategy_id=strategy_id,
                parameter=f"student_param_{i}",
                old_value="0.0",
                new_value=f"{p:.10f}",
                reason=f"distillation step n_steps={state.n_steps}",
                meta={
                    "version": DISTILLATION_VERSION,
                    "n_steps": str(state.n_steps),
                    "final_loss": f"{state.final_loss:.8f}",
                    "digest": state.digest[:8],
                },
            )
        )
    return updates


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


__all__ = [
    "DISTILLATION_VERSION",
    "DistillationConfig",
    "DistillationError",
    "DistillationSample",
    "DistillationState",
    "build_learning_updates",
    "distillation_loss",
    "distillation_step",
    "make_initial_state",
    "soft_cross_entropy",
    "train",
]
