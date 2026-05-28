"""GOV-G17 — Overconfidence guardrail.

Detects when a signal source is systematically overconfident.
Pure state machine — no I/O, no wall-clock reads (INV-15).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OverconfidenceViolation:
    """Snapshot describing a detected overconfidence breach."""

    source: str
    avg_confidence: float
    threshold: float
    sample_count: int


class OverconfidenceGuardrail:
    """Accumulates per-source confidence observations and detects overconfidence.

    A violation is raised when ``avg_confidence >= threshold`` and
    ``sample_count >= min_samples``.
    """

    __slots__ = ("threshold", "min_samples", "_sums", "_counts")

    def __init__(self, threshold: float = 0.85, min_samples: int = 20) -> None:
        self.threshold = threshold
        self.min_samples = min_samples
        self._sums: dict[str, float] = {}
        self._counts: dict[str, int] = {}

    # ------------------------------------------------------------------
    def record(self, source: str, confidence: float) -> None:
        """Record one confidence observation for *source*."""
        self._sums[source] = self._sums.get(source, 0.0) + confidence
        self._counts[source] = self._counts.get(source, 0) + 1

    def check(self, source: str) -> OverconfidenceViolation | None:
        """Return a violation if overconfidence detected, else ``None``."""
        count = self._counts.get(source, 0)
        if count < self.min_samples:
            return None
        avg = self._sums.get(source, 0.0) / count
        if avg >= self.threshold:
            return OverconfidenceViolation(
                source=source,
                avg_confidence=avg,
                threshold=self.threshold,
                sample_count=count,
            )
        return None


__all__ = ["OverconfidenceViolation", "OverconfidenceGuardrail"]
