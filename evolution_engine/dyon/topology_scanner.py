"""
evolution_engine/dyon/topology_scanner.py
DIX VISION v42.2 — DYON Topology Scanner

DYON's autonomous architectural drift detection capability.

Scans Python source files for violations of declared architectural invariants:

  B1  — Cross-engine imports at protected domain boundaries
  L2  — Offline engines (evolution_engine, learning_engine) importing runtime engines
  L3  — Runtime engines importing offline engines (learning_engine, evolution_engine)
  INV-15 — Non-deterministic imports in replay-eligible paths (time, random, datetime)

Results are returned as typed, frozen :class:`TopologyScanResult` records.
Calling :meth:`DyonTopologyScanner.scan_and_emit` additionally publishes
:class:`ArchitecturalDriftEvent` records to the SYSTEM/DYON ledger stream
via :mod:`evolution_engine.charter.dyon_observability_emitter`.

Authority: DYON domain (Domain.SYSTEM). This module must never import
execution_engine or intelligence_engine.cognitive internals (B1).

INV-15: The scanner itself uses the filesystem (not replay-eligible). The
scan results are deterministic given the same file contents.
"""

from __future__ import annotations

import ast
import time
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Rule constants — mirrors tools/authority_lint.py rule definitions
# ---------------------------------------------------------------------------

_RUNTIME_ENGINE_PACKAGES: frozenset[str] = frozenset({
    "intelligence_engine",
    "execution_engine",
    "system_engine",
    "governance_engine",
})

_OFFLINE_ENGINE_PACKAGES: frozenset[str] = frozenset({
    "learning_engine",
    "evolution_engine",
})

_ALL_ENGINE_PACKAGES: frozenset[str] = _RUNTIME_ENGINE_PACKAGES | _OFFLINE_ENGINE_PACKAGES

_ALLOWED_SHARED_PREFIXES: tuple[str, ...] = (
    "core",
    "state.ledger.reader",
)

_B1_EXTRA_ALLOWED_PREFIXES: tuple[str, ...] = (
    "system_engine.authority",
    "system_engine.coupling",
    "system_engine.credentials",
)

# Replay paths are those that must be deterministic (INV-15).
# Imports of wall-clock or PRNG modules in these paths are violations.
_REPLAY_PATH_PREFIXES: tuple[str, ...] = (
    "intelligence_engine.meta_controller",
    "intelligence_engine.signal_pipeline",
    "intelligence_engine.meta",
    "execution_engine.hot_path",
    "state.ledger",
)

# INV-15 exemptions: canonical clock chokepoints that legitimately wrap time.
# Mirrors authority_lint.py B_CLOCK_ALLOWED_PATH_PARTS — any module listed
# here IS the time source abstraction layer and must import time directly.
_INV15_EXEMPT_MODULES: tuple[str, ...] = (
    "execution_engine.hot_path.time_authority",
    "system.time_source",
)

_NON_DETERMINISTIC_STDLIB: tuple[str, ...] = (
    "time",
    "datetime",
    "random",
    "os.urandom",
    "secrets",
    "uuid",
)

_SKIP_DIRS: frozenset[str] = frozenset({
    ".git",
    ".venv",
    "venv",
    ".tox",
    "node_modules",
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".claude",
    "rust",
    "target",
    "tools",
})


# ---------------------------------------------------------------------------
# Typed violation records
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TopologyViolation:
    """A single detected architectural invariant violation."""
    invariant_id: str       # e.g. "B1", "L2", "INV-15"
    rule: str               # human-readable rule name
    source_module: str      # dotted module name of the importing file
    imported_module: str    # dotted module name being imported
    file_path: str          # absolute path of the source file
    line: int               # import line number
    description: str        # violation explanation
    severity: str           # "WARNING" | "CRITICAL"


@dataclass(frozen=True, slots=True)
class TopologyScanResult:
    """Complete result of one topology scan pass."""
    ts_ns: int
    root: str
    files_scanned: int
    violations: tuple[TopologyViolation, ...]
    scan_duration_ms: float

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    @property
    def critical_violations(self) -> tuple[TopologyViolation, ...]:
        return tuple(v for v in self.violations if v.severity == "CRITICAL")

    @property
    def warning_violations(self) -> tuple[TopologyViolation, ...]:
        return tuple(v for v in self.violations if v.severity == "WARNING")

    def is_clean(self) -> bool:
        return len(self.critical_violations) == 0


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _module_name_for(path: Path, root: Path) -> str:
    """Convert a path inside the repo into a dotted module name."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return str(path)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _starts_with_any(name: str, prefixes: tuple[str, ...] | frozenset[str]) -> bool:
    return any(name == p or name.startswith(p + ".") for p in prefixes)


def _iter_imports(tree: ast.AST) -> list[tuple[int, str]]:
    """Return (lineno, dotted_module_name) for every absolute import."""
    results: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:
                continue  # relative imports are always in-package
            results.append((node.lineno, mod))
    return results


def _iter_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for p in root.rglob("*.py"):
        try:
            rel_parts = p.relative_to(root).parts
        except ValueError:
            rel_parts = p.parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        files.append(p)
    return files


# ---------------------------------------------------------------------------
# Rule checkers — return TopologyViolation or None
# ---------------------------------------------------------------------------

def _check_b1(
    importer: str, target: str, file_path: str, line: int
) -> TopologyViolation | None:
    """B1: cross-runtime-engine direct imports forbidden."""
    if not _starts_with_any(importer, _ALL_ENGINE_PACKAGES):
        return None
    if _starts_with_any(target, _ALLOWED_SHARED_PREFIXES):
        return None
    if _starts_with_any(target, _B1_EXTRA_ALLOWED_PREFIXES):
        return None

    importer_pkg = importer.split(".")[0]
    target_pkg = target.split(".")[0]

    if target_pkg in _RUNTIME_ENGINE_PACKAGES and target_pkg != importer_pkg:
        if importer_pkg in _RUNTIME_ENGINE_PACKAGES:
            return TopologyViolation(
                invariant_id="B1",
                rule="cross-engine import",
                source_module=importer,
                imported_module=target,
                file_path=file_path,
                line=line,
                description=(
                    f"Runtime engine '{importer_pkg}' directly imports "
                    f"runtime engine '{target_pkg}' (use core.contracts only)"
                ),
                severity="CRITICAL",
            )
    return None


def _check_l2(
    importer: str, target: str, file_path: str, line: int
) -> TopologyViolation | None:
    """L2: offline engines may not import runtime engines."""
    if not _starts_with_any(importer, _OFFLINE_ENGINE_PACKAGES):
        return None
    if _starts_with_any(target, _ALLOWED_SHARED_PREFIXES):
        return None

    target_pkg = target.split(".")[0]
    if target_pkg in _RUNTIME_ENGINE_PACKAGES:
        return TopologyViolation(
            invariant_id="L2",
            rule="offline→runtime import",
            source_module=importer,
            imported_module=target,
            file_path=file_path,
            line=line,
            description=(
                f"Offline engine '{importer.split('.')[0]}' imports runtime "
                f"engine '{target_pkg}' — offline engines must not depend on runtime"
            ),
            severity="CRITICAL",
        )
    return None


def _check_l3(
    importer: str, target: str, file_path: str, line: int
) -> TopologyViolation | None:
    """L3: runtime engines may not import offline engines."""
    if not _starts_with_any(importer, _RUNTIME_ENGINE_PACKAGES):
        return None
    if _starts_with_any(target, _ALLOWED_SHARED_PREFIXES):
        return None

    target_pkg = target.split(".")[0]
    if target_pkg in _OFFLINE_ENGINE_PACKAGES:
        return TopologyViolation(
            invariant_id="L3",
            rule="runtime→offline import",
            source_module=importer,
            imported_module=target,
            file_path=file_path,
            line=line,
            description=(
                f"Runtime engine '{importer.split('.')[0]}' imports offline "
                f"engine '{target_pkg}' — runtime must remain isolated from offline"
            ),
            severity="CRITICAL",
        )
    return None


def _check_inv15(
    importer: str, target: str, file_path: str, line: int
) -> TopologyViolation | None:
    """INV-15: non-deterministic stdlib imports in replay-eligible paths."""
    if not _starts_with_any(importer, _REPLAY_PATH_PREFIXES):
        return None
    if _starts_with_any(importer, _INV15_EXEMPT_MODULES):
        return None
    # Only flag top-level non-deterministic modules (not submodules that may be safe)
    if _starts_with_any(target, _NON_DETERMINISTIC_STDLIB):
        return TopologyViolation(
            invariant_id="INV-15",
            rule="replay-path non-determinism",
            source_module=importer,
            imported_module=target,
            file_path=file_path,
            line=line,
            description=(
                f"Replay-eligible path '{importer}' imports non-deterministic "
                f"module '{target}' — use caller-supplied timestamps, avoid PRNG"
            ),
            severity="WARNING",
        )
    return None


_ALL_RULE_CHECKERS = (_check_b1, _check_l2, _check_l3, _check_inv15)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class DyonTopologyScanner:
    """DYON's autonomous architectural topology analysis engine.

    Scans Python source files for import boundary violations and emits
    ArchitecturalDriftEvent records via the DYON observability stream.

    Thread safety: scan() and scan_and_emit() are stateless beyond
    parsing — safe to call concurrently from different threads.
    """

    name: str = "dyon_topology_scanner"
    spec_id: str = "DYON-TOPO-01"

    def scan(self, root: Path | str, *, ts_ns: int) -> TopologyScanResult:
        """Scan all Python files under ``root`` for architectural violations.

        Args:
            root: Repository root path to scan.
            ts_ns: Caller-supplied timestamp (INV-15; scanner uses
                wall-clock only for ``scan_duration_ms``).

        Returns:
            Frozen :class:`TopologyScanResult` with all detected violations.
        """
        root = Path(root)
        t0 = time.monotonic()
        python_files = _iter_python_files(root)
        violations: list[TopologyViolation] = []

        for fpath in python_files:
            module_name = _module_name_for(fpath, root)
            try:
                source = fpath.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(fpath))
            except SyntaxError:
                continue
            except OSError:
                continue

            for line, imported in _iter_imports(tree):
                for checker in _ALL_RULE_CHECKERS:
                    v = checker(module_name, imported, str(fpath), line)
                    if v is not None:
                        violations.append(v)

        duration_ms = (time.monotonic() - t0) * 1000.0
        return TopologyScanResult(
            ts_ns=ts_ns,
            root=str(root),
            files_scanned=len(python_files),
            violations=tuple(violations),
            scan_duration_ms=duration_ms,
        )

    def scan_and_emit(self, root: Path | str, *, ts_ns: int) -> TopologyScanResult:
        """Scan and emit :class:`ArchitecturalDriftEvent` for each violation.

        Identical to :meth:`scan` but additionally publishes each violation
        to the SYSTEM/DYON ledger stream via the DYON observability emitter.
        Emission is best-effort — scan results are always returned even if
        ledger writes fail.

        Returns:
            The same :class:`TopologyScanResult` as :meth:`scan`.
        """
        result = self.scan(root, ts_ns=ts_ns)
        self._emit(result)
        return result

    @staticmethod
    def _emit(result: TopologyScanResult) -> None:
        """Best-effort event emission — never raises."""
        try:
            from evolution_engine.charter.dyon_observability_emitter import (
                emit_architectural_drift,
                emit_topology_drift,
            )
            for v in result.violations:
                if v.invariant_id in ("B1", "L2", "L3"):
                    emit_architectural_drift(
                        ts_ns=result.ts_ns,
                        invariant_id=v.invariant_id,
                        violation_description=v.description,
                        severity=v.severity,
                        affected_modules=(v.source_module, v.imported_module),
                        recommended_action=(
                            f"Remove direct import of '{v.imported_module}' "
                            f"from '{v.source_module}'; use core.contracts only."
                        ),
                    )
                elif v.invariant_id == "INV-15":
                    emit_topology_drift(
                        ts_ns=result.ts_ns,
                        module=v.source_module,
                        expected_topology="no non-deterministic imports in replay path",
                        actual_topology=f"imports {v.imported_module!r}",
                        drift_severity="WARNING",
                        description=v.description,
                        recommended_action=(
                            f"Remove '{v.imported_module}' from replay path "
                            f"'{v.source_module}'; inject timestamps via caller."
                        ),
                    )
        except Exception:  # pragma: no cover
            pass


# ---------------------------------------------------------------------------
# Module-level singleton (optional convenience; callers may construct their own)
# ---------------------------------------------------------------------------

_default_scanner: DyonTopologyScanner | None = None


def get_scanner() -> DyonTopologyScanner:
    """Return the module-level singleton scanner."""
    global _default_scanner
    if _default_scanner is None:
        _default_scanner = DyonTopologyScanner()
    return _default_scanner


__all__ = [
    "DyonTopologyScanner",
    "TopologyScanResult",
    "TopologyViolation",
    "get_scanner",
]
