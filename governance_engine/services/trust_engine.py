"""GOV-G13 — Trust scoring engine.

Pure value objects and a clamped scoring state machine.
No I/O, no wall-clock reads (INV-15).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TrustScore:
    """Immutable snapshot of an engine's trust score."""

    engine_id: str
    score: float  # [0.0, 1.0]
    reason: str


class TrustEngine:
    """Per-engine trust ledger.

    Default score is 1.0 for any unseen engine_id.
    All mutations clamp to [0.0, 1.0].
    """

    __slots__ = ("_scores",)

    def __init__(self) -> None:
        self._scores: dict[str, float] = {}

    # ------------------------------------------------------------------
    def score(self, engine_id: str) -> TrustScore:
        """Return the current trust snapshot for *engine_id*."""
        return TrustScore(
            engine_id=engine_id,
            score=self._scores.get(engine_id, 1.0),
            reason="",
        )

    def update(self, engine_id: str, delta: float, *, reason: str) -> TrustScore:
        """Apply *delta* to the score and return the new snapshot."""
        current = self._scores.get(engine_id, 1.0)
        new_score = max(0.0, min(1.0, current + delta))
        self._scores[engine_id] = new_score
        return TrustScore(engine_id=engine_id, score=new_score, reason=reason)

    def revoke(self, engine_id: str, reason: str) -> None:
        """Hard-set score to 0.0 (trust revoked)."""
        self._scores[engine_id] = 0.0


__all__ = ["TrustScore", "TrustEngine"]
