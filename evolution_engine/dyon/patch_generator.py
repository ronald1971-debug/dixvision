"""DyonPatchGenerator — violation → concrete patch instruction (P2 Autonomous Loop).

Converts a TopologyViolation from a topology scan into a grounded,
file-level patch instruction — not a generic suggestion but a specific
action: which file, which line, what to remove or change, and why.

Instruction types:
    REMOVE_IMPORT    — B1 / L2 / L3: delete a forbidden cross-layer import
    REDIRECT_IMPORT  — reroute through core.contracts or an injection seam
    ADD_FROZEN       — INV-08: add frozen=True, slots=True to dataclass
    INJECT_TIMESTAMP — INV-15: replace internal clock with ts_ns parameter
    REVIEW           — unknown invariant; human review required

The generator reads the offending source file (best-effort) to extract
the *exact* import text at the reported line number.  If the file is
unreadable the instruction falls back to module-level guidance.

Authority: evolution_engine.* and core.* only (B1).
INV-15: ts_ns is caller-supplied.
"""

from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# PatchInstruction — the concrete product of this module
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PatchInstruction:
    """Concrete, file-grounded patch instruction produced from one violation.

    Fields:
        patch_id:          Deterministic ID derived from violation context.
        invariant_id:      Which invariant is violated ("B1", "INV-15", …).
        instruction_type:  Action verb (REMOVE_IMPORT, ADD_FROZEN, …).
        target_file:       Repo-relative file path of the offending file.
        target_line:       Approximate line number (0 if unknown).
        import_text:       The exact import statement found at target_line
                           (empty string if file unreadable).
        action:            What DYON proposes: specific edit description.
        rationale:         Why this fix is required (invariant citation).
        diff_hint:         Short pseudo-diff illustrating the change.
        confidence:        DYON's confidence in this fix (0.0–1.0).
        ts_ns:             Timestamp of patch generation.
    """

    patch_id: str
    invariant_id: str
    instruction_type: str
    target_file: str
    target_line: int
    import_text: str
    action: str
    rationale: str
    diff_hint: str
    confidence: float
    ts_ns: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "invariant_id": self.invariant_id,
            "instruction_type": self.instruction_type,
            "target_file": self.target_file,
            "target_line": self.target_line,
            "import_text": self.import_text,
            "action": self.action,
            "rationale": self.rationale,
            "diff_hint": self.diff_hint,
            "confidence": self.confidence,
            "ts_ns": self.ts_ns,
        }


# ---------------------------------------------------------------------------
# PatchGenerator
# ---------------------------------------------------------------------------


class PatchGenerator:
    """Produces concrete PatchInstruction objects from TopologyViolations.

    Args:
        repo_root: Repository root path used to resolve source file paths.
    """

    def __init__(self, repo_root: pathlib.Path | str = ".") -> None:
        self._root = pathlib.Path(repo_root).resolve()

    def generate(self, violation: Any, *, ts_ns: int) -> PatchInstruction | None:
        """Generate a patch instruction for *violation*.

        Returns None only if the violation is malformed (missing required fields).
        Never raises.
        """
        try:
            return self._dispatch(violation, ts_ns=ts_ns)
        except Exception:
            return None

    def _dispatch(self, v: Any, *, ts_ns: int) -> PatchInstruction:
        inv = str(getattr(v, "invariant_id", "") or "")
        if "INV-15" in inv:
            return self._fix_clock(v, ts_ns=ts_ns)
        elif "INV-08" in inv:
            return self._fix_frozen(v, ts_ns=ts_ns)
        elif inv in ("B1", "L2", "L3") or inv.startswith("B") or inv.startswith("L"):
            return self._fix_import(v, ts_ns=ts_ns)
        else:
            return self._generic_review(v, ts_ns=ts_ns)

    # ------------------------------------------------------------------
    # Instruction builders
    # ------------------------------------------------------------------

    def _fix_import(self, v: Any, *, ts_ns: int) -> PatchInstruction:
        """REMOVE_IMPORT — cross-layer import boundary violation."""
        src = str(getattr(v, "source_module", ""))
        imp = str(getattr(v, "imported_module", ""))
        line = int(getattr(v, "line", 0))
        inv = str(getattr(v, "invariant_id", "B1"))

        target_file = self._module_to_path(src)
        import_text = self._read_line(target_file, line) if line else ""

        # Heuristic: if imported_module is in core.contracts, prefer REDIRECT
        if "core" in imp or "contracts" in imp:
            instruction_type = "REDIRECT_IMPORT"
            action = (
                f"In {target_file}:{line} — redirect import of '{imp}' "
                f"to the equivalent symbol in core.contracts or inject via __init__ parameter."
            )
            diff_hint = (
                f"- {import_text or f'from {imp} import ...'}\n"
                f"+ # inject via constructor or use core.contracts equivalent"
            )
            confidence = 0.70
        else:
            instruction_type = "REMOVE_IMPORT"
            action = (
                f"In {target_file}:{line} — remove direct import of '{imp}' "
                f"from '{src}'. This violates {inv} boundary rule. "
                f"Decouple via dependency injection or a shared contract in core/."
            )
            diff_hint = (
                f"- {import_text or f'from {imp} import ...'}\n"
                f"  # remove and inject the dependency through __init__ or a factory"
            )
            confidence = 0.80

        return PatchInstruction(
            patch_id=self._make_patch_id(inv, src, imp, ts_ns),
            invariant_id=inv,
            instruction_type=instruction_type,
            target_file=target_file,
            target_line=line,
            import_text=import_text.strip(),
            action=action,
            rationale=(
                f"{inv} boundary rule violated: '{src}' must not directly import "
                f"from '{imp}'. Layer topology enforces import direction."
            ),
            diff_hint=diff_hint,
            confidence=confidence,
            ts_ns=ts_ns,
        )

    def _fix_frozen(self, v: Any, *, ts_ns: int) -> PatchInstruction:
        """ADD_FROZEN — INV-08: dataclass missing frozen=True, slots=True."""
        src = str(getattr(v, "source_module", ""))
        line = int(getattr(v, "line", 0))

        target_file = self._module_to_path(src)
        import_text = self._read_line(target_file, line) if line else ""

        return PatchInstruction(
            patch_id=self._make_patch_id("INV-08", src, "frozen", ts_ns),
            invariant_id="INV-08",
            instruction_type="ADD_FROZEN",
            target_file=target_file,
            target_line=line,
            import_text=import_text.strip(),
            action=(
                f"In {target_file}:{line} — add frozen=True and slots=True to the "
                f"@dataclass decorator. All cross-boundary contract types must be "
                f"immutable (INV-08)."
            ),
            rationale=(
                "INV-08: cross-domain contract dataclasses must be frozen=True, slots=True "
                "to guarantee immutability at domain boundaries."
            ),
            diff_hint=(
                f"- @dataclass\n"
                f"+ @dataclass(frozen=True, slots=True)\n"
                f"  class {src.split('.')[-1].title()}:"
            ),
            confidence=0.90,
            ts_ns=ts_ns,
        )

    def _fix_clock(self, v: Any, *, ts_ns: int) -> PatchInstruction:
        """INJECT_TIMESTAMP — INV-15: wall-clock read in compute path."""
        src = str(getattr(v, "source_module", ""))
        line = int(getattr(v, "line", 0))

        target_file = self._module_to_path(src)
        import_text = self._read_line(target_file, line) if line else ""

        return PatchInstruction(
            patch_id=self._make_patch_id("INV-15", src, "clock", ts_ns),
            invariant_id="INV-15",
            instruction_type="INJECT_TIMESTAMP",
            target_file=target_file,
            target_line=line,
            import_text=import_text.strip(),
            action=(
                f"In {target_file}:{line} — replace internal wall-clock read "
                f"(time.time_ns(), datetime.now(), etc.) with a caller-supplied "
                f"ts_ns: int parameter. This makes the function replay-deterministic (INV-15)."
            ),
            rationale=(
                "INV-15 replay determinism: same inputs must produce identical outputs. "
                "Internal clock reads make functions non-deterministic across replay runs."
            ),
            diff_hint=(
                f"- ts = time.time_ns()  # or datetime.now()\n"
                f"+ # ts_ns injected by caller — do not read wall clock here\n"
                f"  def method(self, ..., ts_ns: int) -> ...:"
            ),
            confidence=0.75,
            ts_ns=ts_ns,
        )

    def _generic_review(self, v: Any, *, ts_ns: int) -> PatchInstruction:
        """REVIEW — unknown invariant; low-confidence human-review instruction."""
        src = str(getattr(v, "source_module", ""))
        inv = str(getattr(v, "invariant_id", "UNKNOWN"))
        desc = str(getattr(v, "description", ""))

        return PatchInstruction(
            patch_id=self._make_patch_id(inv, src, "review", ts_ns),
            invariant_id=inv,
            instruction_type="REVIEW",
            target_file=self._module_to_path(src),
            target_line=int(getattr(v, "line", 0)),
            import_text="",
            action=f"Manual review required for {inv} in {src}: {desc}",
            rationale=f"Invariant {inv} violated; automated patch not yet supported.",
            diff_hint="# Manual investigation required",
            confidence=0.30,
            ts_ns=ts_ns,
        )

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def _module_to_path(self, module: str) -> str:
        """Convert 'a.b.c' to 'a/b/c.py' relative path string."""
        return module.replace(".", "/") + ".py"

    def _read_line(self, rel_path: str, line_no: int) -> str:
        """Read a single line from the source file. Returns '' on any error."""
        try:
            full = self._root / rel_path
            if not full.exists():
                return ""
            lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
            idx = line_no - 1
            if 0 <= idx < len(lines):
                return lines[idx]
            return ""
        except Exception:
            return ""

    @staticmethod
    def _make_patch_id(inv: str, src: str, imp: str, ts_ns: int) -> str:
        """Deterministic patch ID from violation context."""
        raw = f"{inv}:{src}:{imp}"
        short = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"dyon_pi_{short}_{ts_ns & 0xFFFFFF:06x}"


# ---------------------------------------------------------------------------
# Module-level singleton (repo_root set lazily on first use)
# ---------------------------------------------------------------------------

_generator: PatchGenerator | None = None


def get_patch_generator(
    repo_root: pathlib.Path | str = ".",
) -> PatchGenerator:
    """Return the process-wide PatchGenerator singleton."""
    global _generator
    if _generator is None:
        _generator = PatchGenerator(repo_root=repo_root)
    return _generator


__all__ = [
    "PatchInstruction",
    "PatchGenerator",
    "get_patch_generator",
]
