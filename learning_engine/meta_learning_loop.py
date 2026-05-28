"""Meta-Learning Loop — learns HOW to learn, not just what works.

Standard RL learns: "what works in this market"
Meta-RL learns: "how to adapt when things stop working"

This is the layer that updates learning rules themselves:
- Adjusts learning rates based on environment stability
- Modifies reward weights when conditions change
- Switches between exploration and exploitation
- Detects when the learning signal itself is stale
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum


class LearningMode(StrEnum):
    EXPLOIT = "EXPLOIT"  # stable market, use learned policy
    EXPLORE = "EXPLORE"  # unstable market, try new things
    ADAPT = "ADAPT"  # detected regime shift, rapidly adapting
    RESET = "RESET"  # severe failure, restart learning from scratch


@dataclass(frozen=True, slots=True)
class MetaLearningState:
    """Current state of the meta-learning loop."""

    mode: LearningMode
    learning_rate: float
    exploration_rate: float
    reward_weight_adjustment: dict[str, float]
    stability_score: float  # [0, 1] how stable is the learning signal
    adaptation_speed: float  # how fast we're changing
    cycles_in_mode: int


@dataclass(frozen=True, slots=True)
class MetaUpdate:
    """Update to learning hyperparameters."""

    new_learning_rate: float
    new_exploration_rate: float
    reward_weight_changes: dict[str, float]
    mode_transition: LearningMode | None
    reason: str


class MetaLearningLoop:
    """Adjusts the learning process itself based on meta-signals.

    Monitors:
    - Learning progress rate (are we still improving?)
    - Prediction accuracy trend (are predictions getting better/worse?)
    - Environment stability (is the market behaving as expected?)
    - Strategy diversity (are we converging too much?)

    When these meta-signals indicate problems, adjusts:
    - Learning rate (faster when adapting, slower when stable)
    - Exploration rate (more when stuck, less when performing)
    - Reward weights (shift emphasis when certain factors matter more)
    """

    def __init__(
        self,
        *,
        base_learning_rate: float = 0.001,
        base_exploration_rate: float = 0.1,
        stability_window: int = 50,
        patience: int = 20,
    ) -> None:
        self._base_lr = base_learning_rate
        self._base_explore = base_exploration_rate
        self._window = stability_window
        self._patience = patience
        self._mode = LearningMode.EXPLORE
        self._cycles_in_mode = 0
        self._lr = base_learning_rate
        self._explore = base_exploration_rate
        self._reward_adjustments: dict[str, float] = {}
        self._performance_history: deque[float] = deque(maxlen=stability_window)
        self._prediction_accuracy: deque[float] = deque(maxlen=stability_window)
        self._no_improvement_count = 0

    @property
    def state(self) -> MetaLearningState:
        stability = self._compute_stability()
        return MetaLearningState(
            mode=self._mode,
            learning_rate=self._lr,
            exploration_rate=self._explore,
            reward_weight_adjustment=dict(self._reward_adjustments),
            stability_score=stability,
            adaptation_speed=self._lr / self._base_lr,
            cycles_in_mode=self._cycles_in_mode,
        )

    def tick(
        self,
        *,
        current_performance: float,  # latest performance metric
        prediction_accuracy: float,  # how accurate recent predictions were
        strategy_diversity: float,  # [0, 1] how diverse the strategy pool is
        regime_changed: bool,  # did the regime just change?
    ) -> MetaUpdate:
        """Run one meta-learning cycle. Returns hyperparameter updates."""
        self._performance_history.append(current_performance)
        self._prediction_accuracy.append(prediction_accuracy)
        self._cycles_in_mode += 1

        # Detect if we're still improving
        improving = self._is_improving()
        stability = self._compute_stability()

        # Mode transitions
        new_mode: LearningMode | None = None

        if regime_changed:
            new_mode = LearningMode.ADAPT
            self._lr = self._base_lr * 5.0  # fast adaptation
            self._explore = min(self._base_explore * 3.0, 0.5)
            reason = "Regime change detected — switching to rapid adaptation."

        elif self._mode == LearningMode.ADAPT:
            if stability > 0.7 and self._cycles_in_mode > 10:
                new_mode = LearningMode.EXPLOIT
                self._lr = self._base_lr
                self._explore = self._base_explore * 0.5
                reason = "Adaptation complete — switching to exploitation."
            else:
                reason = "Still adapting to new regime."

        elif self._mode == LearningMode.EXPLOIT:
            if not improving and self._no_improvement_count > self._patience:
                new_mode = LearningMode.EXPLORE
                self._lr = self._base_lr * 2.0
                self._explore = self._base_explore * 2.0
                reason = f"No improvement for {self._no_improvement_count} cycles — exploring."
            elif strategy_diversity < 0.2:
                new_mode = LearningMode.EXPLORE
                self._explore = self._base_explore * 3.0
                reason = "Strategy pool too homogeneous — increasing exploration."
            else:
                reason = "Exploiting learned policy."

        elif self._mode == LearningMode.EXPLORE:
            if improving and prediction_accuracy > 0.6:
                new_mode = LearningMode.EXPLOIT
                self._lr = self._base_lr
                self._explore = self._base_explore * 0.5
                reason = "Found improvement — switching to exploitation."
            elif self._cycles_in_mode > self._patience * 3:
                new_mode = LearningMode.RESET
                self._lr = self._base_lr * 10.0
                self._explore = 0.5
                reason = "Exploration exhausted — resetting learning."
            else:
                reason = "Exploring for new edges."

        elif self._mode == LearningMode.RESET:
            if self._cycles_in_mode > 10:
                new_mode = LearningMode.EXPLORE
                self._lr = self._base_lr * 2.0
                self._explore = self._base_explore * 2.0
                reason = "Reset complete — resuming exploration."
            else:
                reason = "Resetting learning state."
        else:
            reason = "Steady state."

        if new_mode is not None:
            self._mode = new_mode
            self._cycles_in_mode = 0

        # Track improvement
        if improving:
            self._no_improvement_count = 0
        else:
            self._no_improvement_count += 1

        # Reward weight adjustments based on regime
        if prediction_accuracy < 0.4:
            self._reward_adjustments["regime_correctness"] = 0.05  # emphasize regime
        if stability < 0.3:
            self._reward_adjustments["consistency"] = 0.03  # emphasize stability

        return MetaUpdate(
            new_learning_rate=self._lr,
            new_exploration_rate=self._explore,
            reward_weight_changes=dict(self._reward_adjustments),
            mode_transition=new_mode,
            reason=reason,
        )

    def _is_improving(self) -> bool:
        """Check if performance is trending upward."""
        if len(self._performance_history) < 10:
            return True  # assume improving until proven otherwise
        recent = list(self._performance_history)[-10:]
        older = list(self._performance_history)[-20:-10]
        if not older:
            return True
        return sum(recent) / len(recent) > sum(older) / len(older)

    def _compute_stability(self) -> float:
        """How stable is the learning signal (low variance = stable)."""
        if len(self._performance_history) < 10:
            return 0.5
        values = list(self._performance_history)[-20:]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        # Normalize: low variance → high stability
        import math

        std = math.sqrt(variance) if variance > 0 else 0.0
        return max(1.0 - std / (abs(mean) + 0.001), 0.0)
