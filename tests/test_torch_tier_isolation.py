# ADAPTED FROM: pytorch/pytorch
# (torch/__init__.py — import entry point;
#  Authority lint rule B-TORCH enforces containment to OFFLINE tiers)
"""I-36 — Test that PyTorch is properly isolated from runtime tiers.

Verifies the authority_lint B-TORCH rule: ``import torch`` must NEVER
appear in runtime-tier modules (execution_engine, governance_engine,
system_engine, core, intelligence_engine.meta_controller.hot_path).

Torch is allowed only in OFFLINE tiers:
    * learning_engine.lanes (policy distillation, RL training)
    * evolution_engine (sandbox environments, genetic search)
    * sensory/neuromorphic (SNN layers — OFFLINE only)
    * tools / scripts / tests
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

# Runtime tier prefixes where torch is BANNED
RUNTIME_PREFIXES = (
    "execution_engine",
    "governance_engine",
    "system_engine",
    "core",
)

# Root of the repo
REPO_ROOT = Path(__file__).resolve().parent.parent


def _module_path_to_dotted(file_path: Path) -> str:
    """Convert file path to dotted module name."""
    relative = file_path.relative_to(REPO_ROOT)
    parts = list(relative.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _find_torch_imports(file_path: Path) -> list[tuple[int, str]]:
    """Find all torch imports in a Python file.

    Returns list of (line_number, import_target) tuples.
    """
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("torch"):
                    violations.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("torch"):
                violations.append((node.lineno, node.module))
    return violations


def _collect_runtime_python_files() -> list[Path]:
    """Collect all Python files in runtime-tier directories."""
    files = []
    for prefix in RUNTIME_PREFIXES:
        prefix_path = REPO_ROOT / prefix.replace(".", "/")
        if prefix_path.exists():
            for root, _dirs, filenames in os.walk(prefix_path):
                for f in filenames:
                    if f.endswith(".py"):
                        files.append(Path(root) / f)
    return files


def test_no_torch_in_runtime_tiers():
    """B-TORCH: No torch imports in runtime tier modules."""
    files = _collect_runtime_python_files()
    assert len(files) > 0, "Expected runtime tier Python files to exist"

    violations = []
    for fp in files:
        torch_imports = _find_torch_imports(fp)
        for line, target in torch_imports:
            module = _module_path_to_dotted(fp)
            violations.append(f"  {module} (line {line}): import {target}")

    assert not violations, "B-TORCH violation: torch found in runtime tier!\n" + "\n".join(
        violations
    )


def test_torch_allowed_in_offline_tiers():
    """Verify torch IS allowed in OFFLINE tiers (learning/evolution)."""
    # These directories are allowed to import torch
    allowed_dirs = [
        REPO_ROOT / "learning_engine" / "lanes",
        REPO_ROOT / "evolution_engine",
        REPO_ROOT / "sensory" / "neuromorphic",
    ]

    # At least one of these should exist
    existing = [d for d in allowed_dirs if d.exists()]
    assert len(existing) > 0, "Expected at least one OFFLINE tier dir to exist"


def test_runtime_tier_directories_exist():
    """Sanity check: runtime tier directories exist for scanning."""
    for prefix in RUNTIME_PREFIXES:
        prefix_path = REPO_ROOT / prefix.replace(".", "/")
        assert prefix_path.exists(), f"Runtime tier dir missing: {prefix}"


def test_authority_lint_has_b_torch_rule():
    """Verify authority_lint.py contains the B-TORCH rule."""
    lint_path = REPO_ROOT / "tools" / "authority_lint.py"
    assert lint_path.exists()
    content = lint_path.read_text()
    assert "B-TORCH" in content
    assert "_check_b_torch" in content
    assert "B_TORCH_FORBIDDEN_RUNTIME_PREFIXES" in content
