"""GOV-G15 — Triple-window dry-run harness.

Validates a proposed change across three rolling windows. Pure — no I/O.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

_NS_1H = 3_600_000_000_000
_NS_4H = 14_400_000_000_000
_NS_24H = 86_400_000_000_000


@dataclass(frozen=True, slots=True)
class WindowResult:
    """Outcome of a single window validation."""

    window_ns: int
    passed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class DryRunReport:
    """Aggregate dry-run outcome across all three windows."""

    proposal_id: str
    windows: tuple[WindowResult, ...]
    all_passed: bool


class TripleWindowDryRun:
    """Runs the given *validator* callable against three rolling windows.

    The *validator* receives the window size in nanoseconds and returns
    ``True`` (pass) or ``False`` (fail). Pure — no I/O.
    """

    __slots__ = ("windows_ns",)

    def __init__(
        self,
        windows_ns: tuple[int, int, int] = (_NS_1H, _NS_4H, _NS_24H),
    ) -> None:
        self.windows_ns = windows_ns

    def run(
        self,
        proposal_id: str,
        validator: Callable[[int], bool],
    ) -> DryRunReport:
        """Run *validator* for each window; return a :class:`DryRunReport`."""
        results: list[WindowResult] = []
        for w_ns in self.windows_ns:
            passed = validator(w_ns)
            results.append(
                WindowResult(
                    window_ns=w_ns,
                    passed=passed,
                    reason="" if passed else f"validator failed for window {w_ns}ns",
                )
            )
        windows = tuple(results)
        return DryRunReport(
            proposal_id=proposal_id,
            windows=windows,
            all_passed=all(r.passed for r in results),
        )


__all__ = ["WindowResult", "DryRunReport", "TripleWindowDryRun"]
