"""Exposure limit checker — pure notional cap enforcement."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExposureLimitResult:
    """Outcome of an exposure limit check."""

    passed: bool
    notional: float
    limit: float


class ExposureLimits:
    """Checks whether ``notional`` stays within ``max_notional``. Pure."""

    __slots__ = ("max_notional",)

    def __init__(self, max_notional: float) -> None:
        self.max_notional = max_notional

    def check(self, notional: float) -> ExposureLimitResult:
        passed = notional <= self.max_notional
        return ExposureLimitResult(
            passed=passed,
            notional=notional,
            limit=self.max_notional,
        )


__all__ = ["ExposureLimitResult", "ExposureLimits"]
