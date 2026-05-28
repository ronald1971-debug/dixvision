"""Position limit checker — pure functions and thin class wrapper."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PositionLimitResult:
    """Outcome of a position limit check."""

    passed: bool
    qty: float
    limit: float
    reason: str


def check_position_limit(qty: float, limit: float) -> PositionLimitResult:
    """Pure function — returns a :class:`PositionLimitResult`."""
    passed = qty <= limit
    return PositionLimitResult(
        passed=passed,
        qty=qty,
        limit=limit,
        reason="" if passed else f"qty {qty} exceeds limit {limit}",
    )


class PositionLimits:
    """Thin stateful wrapper around :func:`check_position_limit`."""

    __slots__ = ("max_qty",)

    def __init__(self, max_qty: float) -> None:
        self.max_qty = max_qty

    def check(self, qty: float) -> PositionLimitResult:
        return check_position_limit(qty, self.max_qty)


__all__ = ["PositionLimitResult", "check_position_limit", "PositionLimits"]
