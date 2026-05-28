"""GOV-G18 — Governance-side patch pipeline bridge.

Read + route only; never executes patches. Pure in-memory state machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class PatchStage(StrEnum):
    PROPOSED = "PROPOSED"
    SANDBOX = "SANDBOX"
    STATIC_ANALYSIS = "STATIC_ANALYSIS"
    BACKTEST = "BACKTEST"
    SHADOW = "SHADOW"
    CANARY = "CANARY"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True, slots=True)
class PatchRecord:
    """Immutable snapshot of a patch's current pipeline position."""

    patch_id: str
    stage: PatchStage
    ts_ns: int
    reason: str = ""


class PatchPipelineBridge:
    """In-memory patch stage tracker. Read + route only — never executes patches."""

    __slots__ = ("_records",)

    def __init__(self) -> None:
        self._records: dict[str, PatchRecord] = {}

    # ------------------------------------------------------------------
    def record(self, patch: PatchRecord) -> None:
        """Upsert *patch* into the in-memory store (latest write wins)."""
        self._records[patch.patch_id] = patch

    def current_stage(self, patch_id: str) -> PatchStage | None:
        """Return the current stage for *patch_id*, or ``None`` if unknown."""
        rec = self._records.get(patch_id)
        return rec.stage if rec is not None else None

    def all_records(self) -> tuple[PatchRecord, ...]:
        """Return all records sorted by ``ts_ns`` ascending."""
        return tuple(sorted(self._records.values(), key=lambda r: r.ts_ns))


__all__ = ["PatchStage", "PatchRecord", "PatchPipelineBridge"]
