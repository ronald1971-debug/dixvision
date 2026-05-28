"""CORE-12 / FAIL-16 — boot integrity verifier.

Checks that foundation.hash matches the hash of immutable_core/ at
startup. Called by the bootstrap kernel before any engine is started.
A mismatch means the foundation files were modified after the hash was
written — hard fail.

INV-15: Pure function of (foundation_hash_path, immutable_core_path).
B1:     No imports from engine tiers.
"""

from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass

__all__ = ["BootIntegrityResult", "verify_boot", "verify_boot_or_raise"]


@dataclass(frozen=True, slots=True)
class BootIntegrityResult:
    """Outcome of the boot integrity check."""

    passed: bool
    recorded_hash: str
    computed_hash: str
    detail: str


def _hash_directory(path: pathlib.Path) -> str:
    """Compute a BLAKE2b-256 hash over all .py and .lean files in a directory.

    Files are processed in deterministic sorted order so the hash is
    reproducible across runs (INV-15). Only regular files are included;
    __pycache__ and .pyc files are excluded.
    """
    h = hashlib.blake2b(digest_size=32)
    for file in sorted(path.rglob("*")):
        if not file.is_file():
            continue
        if "__pycache__" in file.parts:
            continue
        if file.suffix not in {".py", ".lean", ".hash"}:
            continue
        if file.name == "foundation.hash":
            continue
        h.update(file.name.encode("utf-8"))
        h.update(file.read_bytes())
    return h.hexdigest()


def verify_boot(
    foundation_hash_path: str | pathlib.Path,
    immutable_core_path: str | pathlib.Path,
) -> BootIntegrityResult:
    """Verify immutable_core/ against foundation.hash.

    Returns a :class:`BootIntegrityResult`; never raises (use
    :func:`verify_boot_or_raise` for hard-fail behaviour).
    """
    fhp = pathlib.Path(foundation_hash_path)
    icp = pathlib.Path(immutable_core_path)

    if not fhp.exists():
        return BootIntegrityResult(
            passed=False,
            recorded_hash="",
            computed_hash="",
            detail=f"foundation.hash not found: {fhp}",
        )
    if not icp.is_dir():
        return BootIntegrityResult(
            passed=False,
            recorded_hash="",
            computed_hash="",
            detail=f"immutable_core/ not found: {icp}",
        )

    recorded = fhp.read_text(encoding="utf-8").strip()
    computed = _hash_directory(icp)

    passed = recorded == computed
    return BootIntegrityResult(
        passed=passed,
        recorded_hash=recorded,
        computed_hash=computed,
        detail="OK" if passed else f"hash mismatch: recorded={recorded[:16]}… computed={computed[:16]}…",
    )


def verify_boot_or_raise(
    foundation_hash_path: str | pathlib.Path,
    immutable_core_path: str | pathlib.Path,
) -> BootIntegrityResult:
    """Like :func:`verify_boot` but raises :class:`RuntimeError` on failure."""
    result = verify_boot(foundation_hash_path, immutable_core_path)
    if not result.passed:
        raise RuntimeError(
            f"Boot integrity check FAILED (CORE-12/FAIL-16): {result.detail}"
        )
    return result
