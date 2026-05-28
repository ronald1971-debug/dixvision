"""FeatureDiscoverer — finds features whose predictive power has changed.

Tracks feature importance over time and alerts when:
- A previously unimportant feature becomes predictive
- An important feature loses predictive power
- New combinations of features become significant
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum


class FeatureStatus(StrEnum):
    EMERGING = "EMERGING"  # becoming predictive (new edge)
    STABLE = "STABLE"  # consistently predictive
    DECAYING = "DECAYING"  # losing predictive power
    DEAD = "DEAD"  # no longer predictive


@dataclass(frozen=True, slots=True)
class DiscoveredFeature:
    """A feature whose predictive power has changed."""

    feature_name: str
    status: FeatureStatus
    current_importance: float  # [0, 1]
    previous_importance: float
    importance_delta: float
    confidence: float
    suggestion: str


class FeatureDiscoverer:
    """Monitors feature importance trends over time.

    Maintains a rolling window of feature importance scores and
    detects significant changes (emergence or decay).
    """

    def __init__(
        self,
        *,
        window_size: int = 50,
        emergence_threshold: float = 0.3,
        decay_threshold: float = -0.2,
    ) -> None:
        self._window = window_size
        self._emerge_thresh = emergence_threshold
        self._decay_thresh = decay_threshold
        self._history: dict[str, deque[float]] = {}

    def update(self, feature_importances: dict[str, float]) -> list[DiscoveredFeature]:
        """Update with new feature importance scores; return discoveries."""
        discoveries: list[DiscoveredFeature] = []

        for name, importance in feature_importances.items():
            if name not in self._history:
                self._history[name] = deque(maxlen=self._window)
            self._history[name].append(importance)

            history = self._history[name]
            if len(history) < 10:
                continue

            # Compare recent vs historical
            recent = list(history)[-5:]
            older = list(history)[:-5]
            recent_avg = sum(recent) / len(recent)
            older_avg = sum(older) / len(older) if older else 0.0
            delta = recent_avg - older_avg

            if delta > self._emerge_thresh:
                discoveries.append(
                    DiscoveredFeature(
                        feature_name=name,
                        status=FeatureStatus.EMERGING,
                        current_importance=recent_avg,
                        previous_importance=older_avg,
                        importance_delta=delta,
                        confidence=min(abs(delta) / 0.5, 0.95),
                        suggestion=(
                            f"Feature '{name}' gaining predictive power."
                            " Consider adding to active signals."
                        ),
                    )
                )
            elif delta < self._decay_thresh:
                discoveries.append(
                    DiscoveredFeature(
                        feature_name=name,
                        status=FeatureStatus.DECAYING,
                        current_importance=recent_avg,
                        previous_importance=older_avg,
                        importance_delta=delta,
                        confidence=min(abs(delta) / 0.5, 0.95),
                        suggestion=(
                            f"Feature '{name}' losing power. Consider removing or replacing."
                        ),
                    )
                )

        return discoveries
