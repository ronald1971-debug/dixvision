"""DIX v42 — boot integrity verifier.

Runs verify_boot against the immutable core and reports the result.
Exits 0 on success, 1 on failure.

Usage:
    python scripts/verify.py [--hash-path PATH] [--core-path PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(_ROOT))

_DEFAULT_HASH_PATH = _ROOT / "integrity" / "boot_hash.txt"
_DEFAULT_CORE_PATH = _ROOT / "core"


def main() -> None:
    parser = argparse.ArgumentParser(description="DIX boot integrity verifier")
    parser.add_argument(
        "--hash-path",
        type=Path,
        default=_DEFAULT_HASH_PATH,
        help="Path to stored boot hash file",
    )
    parser.add_argument(
        "--core-path",
        type=Path,
        default=_DEFAULT_CORE_PATH,
        help="Path to immutable core directory",
    )
    parser.add_argument("--write", action="store_true",
                        help="Write current hash to --hash-path instead of verifying")
    args = parser.parse_args()

    from integrity.verify_boot import verify_boot, _hash_directory

    if args.write:
        current_hash = _hash_directory(args.core_path)
        args.hash_path.parent.mkdir(parents=True, exist_ok=True)
        args.hash_path.write_text(current_hash)
        print(f"Boot hash written: {current_hash}")
        print(f"  → {args.hash_path}")
        sys.exit(0)

    if not args.hash_path.exists():
        print(f"ERROR: Hash file not found: {args.hash_path}")
        print("Run with --write to generate initial hash.")
        sys.exit(1)

    result = verify_boot(
        foundation_hash_path=args.hash_path,
        immutable_core_path=args.core_path,
    )

    if result.passed:
        print(f"Boot integrity OK  — hash={result.actual_hash[:12]}...")
        sys.exit(0)
    else:
        print(f"Boot integrity FAIL")
        print(f"  expected: {result.expected_hash}")
        print(f"  actual:   {result.actual_hash}")
        sys.exit(1)


if __name__ == "__main__":
    main()
