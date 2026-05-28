"""immutable_core/foundation.py — Foundation integrity verification.

DIX VISION v42.2 § S8: The foundation hash is the SHA-256 of this file.
At boot time (bootstrap_kernel.py), FoundationIntegrity.verify() compares
the on-disk hash (immutable_core/foundation.hash) against the live hash
of this file.  If they disagree in prod mode the kill switch fires.

This module is intentionally minimal and uses only stdlib — no third-party
imports are permitted (axiom S9).

Regenerate the hash after any edit:
    python scripts/generate_hash.py
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

# The recorded expected hash (read from foundation.hash at import time
# if available; empty string otherwise).
_HASH_FILE = Path(__file__).parent / "foundation.hash"
EXPECTED_FOUNDATION_HASH: str = _HASH_FILE.read_text().strip() if _HASH_FILE.exists() else ""


class FoundationIntegrity:
    """Verifies that immutable_core/foundation.py has not been tampered with."""

    def __init__(self, *, root: Path | None = None, expected_hash: str = "") -> None:
        self._root = root or Path(__file__).parent.parent
        self._expected = expected_hash or EXPECTED_FOUNDATION_HASH

    def compute_hash(self) -> str:
        """Return SHA-256 hex digest of this file."""
        foundation_path = self._root / "immutable_core" / "foundation.py"
        if not foundation_path.exists():
            return ""
        return hashlib.sha256(foundation_path.read_bytes()).hexdigest()

    def verify(self) -> bool:
        """Return True if the current hash matches the expected hash.

        In non-strict mode (DIX_STRICT_INTEGRITY=0, the default for dev),
        a missing or empty expected hash is treated as passing.
        """
        strict = os.environ.get("DIX_STRICT_INTEGRITY", "0") == "1"
        current = self.compute_hash()

        if not self._expected:
            return not strict

        return current == self._expected


def get_current_foundation_hash() -> str:
    """Compute and return the current foundation hash."""
    fi = FoundationIntegrity()
    return fi.compute_hash()


def verify_foundation() -> bool:
    """Verify foundation integrity (convenience function)."""
    fi = FoundationIntegrity()
    return fi.verify()
