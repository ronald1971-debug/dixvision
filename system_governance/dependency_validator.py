"""
system_governance/dependency_validator.py
DIX VISION v42.2 — Dependency Validator

Declared dependencies must match runtime reality. This validator
compares what a module declares it needs (its dependency manifest)
against what it actually imports at runtime.

Gaps in either direction are flagged:
  - undeclared: imported at runtime but not in the manifest
  - missing: declared in the manifest but not importable at runtime

A module that passes has passed=True in its DependencyValidationResult.
"""

from __future__ import annotations

import importlib
import threading
import time as _time
from collections import deque
from typing import Any

from core.contracts.system_governance import DependencyValidationResult
from state.ledger.event_store import append_event


_MAX_HISTORY = 500


class DependencyValidator:
    """
    Validates that a module's declared dependencies match runtime reality.

    Thread-safe. Callers register a module's declared deps via
    register_manifest() and then call validate() to check them.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # module → tuple of declared dep names
        self._manifests: dict[str, tuple[str, ...]] = {}
        self._results: deque[DependencyValidationResult] = deque(maxlen=_MAX_HISTORY)
        self._violation_count: int = 0

    # ------------------------------------------------------------------
    # Manifest registration
    # ------------------------------------------------------------------

    def register_manifest(self, module: str, declared_deps: tuple[str, ...]) -> None:
        """Register the declared dependency manifest for a module."""
        with self._lock:
            self._manifests[module] = declared_deps

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(
        self,
        module: str,
        runtime_deps: tuple[str, ...] | None = None,
    ) -> DependencyValidationResult:
        """
        Validate a module's declared deps against its runtime imports.

        runtime_deps: the actual imports observed at runtime. If None,
        the validator attempts to probe importability of declared deps.

        Returns a DependencyValidationResult. Violations are emitted to
        the governance ledger.
        """
        ts_ns = _time.time_ns()

        with self._lock:
            declared = self._manifests.get(module, ())

        if runtime_deps is None:
            # Probe: try to import each declared dep
            importable = tuple(d for d in declared if _is_importable(d))
            missing = tuple(d for d in declared if d not in importable)
            undeclared: tuple[str, ...] = ()
            runtime_deps = importable
        else:
            declared_set = set(declared)
            runtime_set = set(runtime_deps)
            undeclared = tuple(sorted(runtime_set - declared_set))
            missing = tuple(sorted(declared_set - runtime_set))

        passed = len(undeclared) == 0 and len(missing) == 0
        detail_parts: list[str] = []
        if undeclared:
            detail_parts.append(f"undeclared: {list(undeclared)}")
        if missing:
            detail_parts.append(f"missing: {list(missing)}")
        detail = "; ".join(detail_parts) if detail_parts else "OK"

        result = DependencyValidationResult(
            ts_ns=ts_ns,
            module=module,
            declared_deps=tuple(declared),
            runtime_deps=tuple(runtime_deps),
            undeclared=undeclared,
            missing=missing,
            passed=passed,
            detail=detail,
        )

        with self._lock:
            self._results.append(result)
            if not passed:
                self._violation_count += 1

        if not passed:
            append_event(
                "GOVERNANCE",
                "SYSGOV_DEPENDENCY_VIOLATION",
                "system_governance.dependency_validator",
                {
                    "module": module,
                    "undeclared": list(undeclared),
                    "missing": list(missing),
                    "detail": detail,
                },
            )

        return result

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def violation_count(self) -> int:
        with self._lock:
            return self._violation_count

    def recent_results(self, n: int = 20) -> list[DependencyValidationResult]:
        with self._lock:
            items = list(self._results)
        return items[-n:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "registered_manifests": len(self._manifests),
                "violation_count": self._violation_count,
                "history_size": len(self._results),
            }


def _is_importable(module_name: str) -> bool:
    """Return True if a module can be successfully imported."""
    try:
        importlib.util.find_spec(module_name)
        return True
    except (ModuleNotFoundError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: DependencyValidator | None = None
_lock = threading.Lock()


def get_dependency_validator() -> DependencyValidator:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = DependencyValidator()
    return _instance


__all__ = ["DependencyValidator", "get_dependency_validator"]
