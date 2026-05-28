"""Cockpit audit — decision diff viewer.

Computes and formats diffs between consecutive AI decision payloads
for operator review. Pure computation. B1. INV-15.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["DecisionDiff", "DecisionDiffer"]


@dataclass(frozen=True, slots=True)
class FieldDiff:
    field: str
    before: Any
    after: Any


@dataclass(frozen=True, slots=True)
class DecisionDiff:
    ts_ns: int
    strategy_id: str
    field_diffs: tuple[FieldDiff, ...]
    added_fields: tuple[str, ...]
    removed_fields: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.field_diffs or self.added_fields or self.removed_fields)


class DecisionDiffer:
    """Compute structural diff between two decision payload dicts."""

    def diff(
        self,
        ts_ns: int,
        strategy_id: str,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> DecisionDiff:
        before_keys = set(before.keys())
        after_keys = set(after.keys())
        added = tuple(sorted(after_keys - before_keys))
        removed = tuple(sorted(before_keys - after_keys))
        common = before_keys & after_keys
        field_diffs = tuple(
            FieldDiff(field=k, before=before[k], after=after[k])
            for k in sorted(common)
            if before[k] != after[k]
        )
        return DecisionDiff(
            ts_ns=ts_ns,
            strategy_id=strategy_id,
            field_diffs=field_diffs,
            added_fields=added,
            removed_fields=removed,
        )

    def format_diff(self, diff: DecisionDiff) -> str:
        lines: list[str] = [f"Decision diff — strategy={diff.strategy_id}"]
        for fd in diff.field_diffs:
            lines.append(f"  ~ {fd.field}: {fd.before!r} → {fd.after!r}")
        for f in diff.added_fields:
            lines.append(f"  + {f}")
        for f in diff.removed_fields:
            lines.append(f"  - {f}")
        if not diff.has_changes:
            lines.append("  (no changes)")
        return "\n".join(lines)
