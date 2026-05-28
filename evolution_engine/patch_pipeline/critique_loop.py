"""evolution_engine/patch_pipeline/critique_loop.py
DIX VISION v42.2 — Critique Loop

Implements an iterative critique-and-refine cycle for proposed patches
before they enter the sandbox or production pipeline. Each patch is
evaluated against a set of CritiqueChecks; failing checks block promotion
until resolved or explicitly overridden by an operator.

Thread-safe. Immutable value objects. No IO in core logic (INV-15).
"""

from __future__ import annotations

import threading
import time as _time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable


class CritiqueVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


class CritiqueSeverity(StrEnum):
    BLOCKING = "BLOCKING"    # must pass for patch to proceed
    WARNING = "WARNING"      # reported but does not block
    INFO = "INFO"


@dataclass(frozen=True, slots=True)
class CritiqueCheck:
    """A single critique check definition."""
    check_id: str
    name: str
    severity: CritiqueSeverity
    description: str = ""


@dataclass(frozen=True, slots=True)
class CritiqueResult:
    """Result of applying one check to one patch."""
    check_id: str
    verdict: CritiqueVerdict
    message: str
    ts_ns: int


@dataclass(frozen=True, slots=True)
class CritiqueReport:
    """Aggregated critique report for one patch version."""
    report_id: str
    patch_id: str
    iteration: int
    results: tuple[CritiqueResult, ...]
    blocked: bool           # True if any BLOCKING check FAILed
    ts_ns: int

    @property
    def passed(self) -> bool:
        return not self.blocked

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if r.verdict == CritiqueVerdict.FAIL)

    @property
    def warn_count(self) -> int:
        return sum(1 for r in self.results if r.verdict == CritiqueVerdict.WARN)


# Type alias for a check evaluator function
CheckFn = Callable[[str, dict[str, Any]], CritiqueVerdict]


class CritiqueLoop:
    """
    Manages iterative critique-and-refine cycles for patches.

    Thread-safe. Callers register checks, then call evaluate(patch_id,
    patch_data) to run all checks. Reports are stored per patch_id.
    """

    def __init__(self, max_iterations: int = 5) -> None:
        self._lock = threading.Lock()
        self._checks: dict[str, tuple[CritiqueCheck, CheckFn]] = {}
        self._reports: dict[str, list[CritiqueReport]] = {}
        self._max_iterations = max_iterations

    def register_check(
        self,
        check: CritiqueCheck,
        fn: CheckFn,
    ) -> None:
        with self._lock:
            self._checks[check.check_id] = (check, fn)

    def evaluate(
        self,
        patch_id: str,
        patch_data: dict[str, Any],
        ts_ns: int | None = None,
    ) -> CritiqueReport:
        """Run all registered checks against patch_data."""
        ts_ns = ts_ns or _time.time_ns()

        with self._lock:
            checks = list(self._checks.values())
            iteration = len(self._reports.get(patch_id, [])) + 1

        results: list[CritiqueResult] = []
        blocked = False

        for check, fn in checks:
            try:
                verdict = fn(patch_id, patch_data)
            except Exception as exc:
                verdict = CritiqueVerdict.FAIL
                results.append(CritiqueResult(
                    check_id=check.check_id,
                    verdict=CritiqueVerdict.FAIL,
                    message=f"check_exception: {exc}",
                    ts_ns=ts_ns,
                ))
                if check.severity == CritiqueSeverity.BLOCKING:
                    blocked = True
                continue

            msg = verdict.value
            results.append(CritiqueResult(
                check_id=check.check_id,
                verdict=verdict,
                message=msg,
                ts_ns=ts_ns,
            ))
            if verdict == CritiqueVerdict.FAIL and check.severity == CritiqueSeverity.BLOCKING:
                blocked = True

        report = CritiqueReport(
            report_id=str(uuid.uuid4()),
            patch_id=patch_id,
            iteration=iteration,
            results=tuple(results),
            blocked=blocked,
            ts_ns=ts_ns,
        )

        with self._lock:
            if patch_id not in self._reports:
                self._reports[patch_id] = []
            self._reports[patch_id].append(report)

        return report

    def history(self, patch_id: str) -> list[CritiqueReport]:
        with self._lock:
            return list(self._reports.get(patch_id, []))

    def latest(self, patch_id: str) -> CritiqueReport | None:
        with self._lock:
            rpts = self._reports.get(patch_id, [])
            return rpts[-1] if rpts else None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "checks": len(self._checks),
                "patches": len(self._reports),
                "max_iterations": self._max_iterations,
            }


# Singleton factory
_instance: CritiqueLoop | None = None
_lock = threading.Lock()


def get_critique_loop() -> CritiqueLoop:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = CritiqueLoop()
    return _instance


__all__ = [
    "CheckFn",
    "CritiqueCheck",
    "CritiqueLoop",
    "CritiqueReport",
    "CritiqueResult",
    "CritiqueSeverity",
    "CritiqueVerdict",
    "get_critique_loop",
]
