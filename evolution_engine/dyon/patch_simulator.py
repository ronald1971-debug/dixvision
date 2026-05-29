"""DyonPatchSimulator — in-memory impact simulation for architectural patches.

Takes a PatchInstruction from PatchGenerator, applies the proposed edit
in-memory (no filesystem writes), re-scans the modified source using the
topology invariant checkers, and determines whether the target violation
would be resolved without introducing new violations.

Results are recorded in DyonMemory (APPROVED / REJECTED / DEFERRED) to
close DYON's self-improvement loop.  This is the "impact simulation" and
"validation" step from the P2 Autonomous DYON Loop directive.

Supported instruction types:
    REMOVE_IMPORT    — removes the forbidden import line; re-scans to confirm
    REDIRECT_IMPORT  — substitutes comment redirect; re-scans to confirm
    ADD_FROZEN       — verifies frozen annotation applicable and syntactically valid
    INJECT_TIMESTAMP — complex rewrite; DEFERRED (requires human review)
    REVIEW           — explicitly DEFERRED

Authority (evolution_engine.*): imports only from evolution_engine.dyon.*
and standard library.  No intelligence_engine, governance_engine, or
runtime_engine imports (L2).
INV-15: ts_ns is caller-supplied; no wall-clock reads.
"""

from __future__ import annotations

import ast
import logging
import pathlib
from dataclasses import dataclass
from typing import Any

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PatchSimulationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PatchSimulationResult:
    """Frozen result of simulating one PatchInstruction in memory."""

    patch_id: str
    instruction_type: str
    target_file: str
    outcome: str                  # "APPROVED" | "REJECTED" | "DEFERRED"
    violation_resolved: bool
    new_violations_introduced: int
    confidence: float             # 0.0–1.0 after simulation discount
    notes: str
    ts_ns: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "instruction_type": self.instruction_type,
            "target_file": self.target_file,
            "outcome": self.outcome,
            "violation_resolved": self.violation_resolved,
            "new_violations_introduced": self.new_violations_introduced,
            "confidence": self.confidence,
            "notes": self.notes,
            "ts_ns": self.ts_ns,
        }


# ---------------------------------------------------------------------------
# DyonPatchSimulator
# ---------------------------------------------------------------------------


class DyonPatchSimulator:
    """Applies PatchInstructions as in-memory dry-runs and validates impact.

    Thread-safe: all public methods are stateless or use only locals.

    Args:
        repo_root: Repository root used to resolve relative file paths and to
            derive dotted module names for the invariant re-scan.
    """

    def __init__(self, repo_root: str | pathlib.Path = ".") -> None:
        self._repo_root = pathlib.Path(repo_root).resolve()

    def simulate(self, instruction: Any, *, ts_ns: int) -> PatchSimulationResult:
        """Dry-run one PatchInstruction and record the outcome in DyonMemory.

        Args:
            instruction: A PatchInstruction from PatchGenerator.
            ts_ns: Caller-supplied timestamp (INV-15).

        Returns:
            Frozen PatchSimulationResult.  Never raises.
        """
        itype = str(getattr(instruction, "instruction_type", "REVIEW")).upper()

        try:
            if itype in ("REMOVE_IMPORT", "REDIRECT_IMPORT"):
                result = self._simulate_import_removal(instruction, ts_ns=ts_ns)
            elif itype == "ADD_FROZEN":
                result = self._simulate_add_frozen(instruction, ts_ns=ts_ns)
            else:
                result = self._deferred(
                    instruction, ts_ns=ts_ns,
                    notes=f"type={itype}_requires_human_review",
                )
        except Exception as exc:
            _logger.debug("DyonPatchSimulator.simulate error on %s: %s",
                          getattr(instruction, "patch_id", "?"), exc)
            result = self._rejected(instruction, ts_ns, f"internal_error:{exc}")

        self._record_outcome(instruction, result, ts_ns=ts_ns)
        return result

    def simulate_batch(
        self,
        instructions: list[Any],
        *,
        ts_ns: int,
    ) -> list[PatchSimulationResult]:
        """Simulate a batch of PatchInstructions.  Never raises."""
        results: list[PatchSimulationResult] = []
        for instr in instructions:
            results.append(self.simulate(instr, ts_ns=ts_ns))
        return results

    # ------------------------------------------------------------------
    # Import removal / redirect simulation
    # ------------------------------------------------------------------

    def _simulate_import_removal(
        self, instruction: Any, *, ts_ns: int
    ) -> PatchSimulationResult:
        source = self._read_file(instruction.target_file)
        if source is None:
            return self._rejected(instruction, ts_ns, "file_unreadable")

        orig_violations = self._scan_imports(instruction.target_file, source)

        modified = self._remove_import_line(source, instruction.import_text)
        if modified is None:
            return self._rejected(instruction, ts_ns, "import_line_not_found_in_source")

        if not self._valid_python(modified):
            return self._rejected(instruction, ts_ns, "modified_source_has_syntax_error")

        mod_violations = self._scan_imports(instruction.target_file, modified)

        orig_n = len(orig_violations)
        mod_n = len(mod_violations)
        resolved = mod_n < orig_n
        new_viol = max(0, mod_n - orig_n)
        outcome = "APPROVED" if resolved and new_viol == 0 else "REJECTED"
        confidence = round(instruction.confidence * (1.0 if resolved else 0.35), 3)
        notes = f"orig_violations={orig_n} mod_violations={mod_n} new={new_viol}"

        return PatchSimulationResult(
            patch_id=instruction.patch_id,
            instruction_type=instruction.instruction_type,
            target_file=instruction.target_file,
            outcome=outcome,
            violation_resolved=resolved,
            new_violations_introduced=new_viol,
            confidence=confidence,
            notes=notes,
            ts_ns=ts_ns,
        )

    # ------------------------------------------------------------------
    # ADD_FROZEN simulation
    # ------------------------------------------------------------------

    def _simulate_add_frozen(
        self, instruction: Any, *, ts_ns: int
    ) -> PatchSimulationResult:
        source = self._read_file(instruction.target_file)
        if source is None:
            return self._rejected(instruction, ts_ns, "file_unreadable")

        modified = self._apply_add_frozen(source, instruction.target_line)
        if modified is None:
            return self._rejected(instruction, ts_ns, "dataclass_decorator_not_found_near_target_line")

        if not self._valid_python(modified):
            return self._rejected(instruction, ts_ns, "modified_source_has_syntax_error")

        already_present = modified == source
        return PatchSimulationResult(
            patch_id=instruction.patch_id,
            instruction_type=instruction.instruction_type,
            target_file=instruction.target_file,
            outcome="APPROVED",
            violation_resolved=not already_present,
            new_violations_introduced=0,
            confidence=instruction.confidence,
            notes="frozen_annotation_already_present" if already_present
                  else "frozen_annotation_applicable_and_syntactically_valid",
            ts_ns=ts_ns,
        )

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _read_file(self, file_path: str) -> str | None:
        try:
            p = pathlib.Path(file_path)
            if not p.is_absolute():
                p = self._repo_root / p
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    # ------------------------------------------------------------------
    # In-memory import scan
    # ------------------------------------------------------------------

    def _scan_imports(self, file_path: str, source: str) -> list[Any]:
        """Run all invariant checkers on source string; return violations."""
        from evolution_engine.dyon.topology_scanner import (
            _ALL_RULE_CHECKERS,
            _iter_imports,
            _module_name_for,
        )
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        p = pathlib.Path(file_path)
        if not p.is_absolute():
            p = self._repo_root / p
        module_name = _module_name_for(p, self._repo_root)
        violations: list[Any] = []
        for line, imported in _iter_imports(tree):
            for checker in _ALL_RULE_CHECKERS:
                v = checker(module_name, imported, str(p), line)
                if v is not None:
                    violations.append(v)
        return violations

    # ------------------------------------------------------------------
    # Patch application helpers (in-memory only)
    # ------------------------------------------------------------------

    @staticmethod
    def _remove_import_line(source: str, import_text: str) -> str | None:
        """Remove the first line whose content matches import_text."""
        needle = import_text.strip()
        if not needle:
            return None
        lines = source.splitlines(keepends=True)
        found = False
        new_lines: list[str] = []
        for line in lines:
            if not found and needle in line.strip():
                found = True
            else:
                new_lines.append(line)
        return "".join(new_lines) if found else None

    @staticmethod
    def _apply_add_frozen(source: str, target_line: int) -> str | None:
        """Add frozen=True, slots=True to the @dataclass decorator near target_line.

        Returns unmodified source if already frozen (no-op), modified source
        with the annotation added, or None if no @dataclass found near target_line.
        """
        lines = source.splitlines(keepends=True)
        lo = max(0, target_line - 10)
        hi = min(len(lines), target_line + 10)
        for i in range(lo, hi):
            stripped = lines[i].strip()
            if stripped.startswith("@dataclass"):
                if "frozen=True" in stripped:
                    return source  # already frozen — no-op
                indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
                if "(" in stripped:
                    lines[i] = (
                        lines[i].rstrip().rstrip(")").rstrip(", ")
                        + ", frozen=True, slots=True)\n"
                    )
                else:
                    lines[i] = indent + "@dataclass(frozen=True, slots=True)\n"
                return "".join(lines)
        return None

    @staticmethod
    def _valid_python(source: str) -> bool:
        try:
            ast.parse(source)
            return True
        except SyntaxError:
            return False

    # ------------------------------------------------------------------
    # Result constructors
    # ------------------------------------------------------------------

    def _rejected(
        self, instruction: Any, ts_ns: int, notes: str
    ) -> PatchSimulationResult:
        return PatchSimulationResult(
            patch_id=instruction.patch_id,
            instruction_type=instruction.instruction_type,
            target_file=instruction.target_file,
            outcome="REJECTED",
            violation_resolved=False,
            new_violations_introduced=0,
            confidence=0.0,
            notes=notes,
            ts_ns=ts_ns,
        )

    def _deferred(
        self, instruction: Any, *, ts_ns: int, notes: str
    ) -> PatchSimulationResult:
        return PatchSimulationResult(
            patch_id=instruction.patch_id,
            instruction_type=instruction.instruction_type,
            target_file=instruction.target_file,
            outcome="DEFERRED",
            violation_resolved=False,
            new_violations_introduced=0,
            confidence=round(instruction.confidence * 0.5, 3),
            notes=notes,
            ts_ns=ts_ns,
        )

    # ------------------------------------------------------------------
    # DyonMemory integration (best-effort)
    # ------------------------------------------------------------------

    @staticmethod
    def _record_outcome(
        instruction: Any, result: PatchSimulationResult, *, ts_ns: int
    ) -> None:
        try:
            from evolution_engine.dyon.dyon_memory import get_dyon_memory
            vkey = (
                f"{instruction.invariant_id}"
                f":{getattr(instruction, 'source_module', instruction.target_file)}"
            )
            get_dyon_memory().record_patch_outcome(
                patch_id=instruction.patch_id,
                violation_key=vkey,
                outcome=result.outcome,
                ts_ns=ts_ns,
                notes=result.notes[:120],
            )
        except Exception as exc:
            _logger.debug("DyonPatchSimulator._record_outcome error: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_simulator: DyonPatchSimulator | None = None


def get_patch_simulator(
    repo_root: str | pathlib.Path = ".",
) -> DyonPatchSimulator:
    """Return the process-wide DyonPatchSimulator singleton."""
    global _simulator
    if _simulator is None:
        _simulator = DyonPatchSimulator(repo_root=repo_root)
    return _simulator


__all__ = [
    "DyonPatchSimulator",
    "PatchSimulationResult",
    "get_patch_simulator",
]
