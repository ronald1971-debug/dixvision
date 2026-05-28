"""tools/replay_validator.py
DIX VISION v42.2 — Replay Validator

CLI tool and library for validating ledger replay determinism (INV-15).
Runs the same replay twice with identical parameters and verifies that
both runs produce the same checksum.

Usage:
    python tools/replay_validator.py --stream SYSTEM --since 0
    python tools/replay_validator.py --stream GOVERNANCE --limit 100

Exit codes:
    0 — replay is deterministic
    1 — replay produced divergent checksums (non-determinism detected)
    2 — error (missing data, import failure, etc.)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class ValidationResult:
    """Result of a replay validation run."""
    stream_kind: str
    since_ts_ns: int
    limit: int | None
    event_count: int
    checksum_run1: str
    checksum_run2: str
    deterministic: bool
    detail: str


def validate_replay(
    stream_kind: str,
    since_ts_ns: int = 0,
    until_ts_ns: int | None = None,
    limit: int | None = None,
    ts_ns: int = 0,
) -> ValidationResult:
    """
    Run the ledger reconstructor twice and compare checksums.

    Returns a ValidationResult indicating whether the replay is
    deterministic (INV-15 compliant).
    """
    try:
        from state.ledger.reconstructor import get_ledger_reconstructor
    except ImportError as exc:
        return ValidationResult(
            stream_kind=stream_kind,
            since_ts_ns=since_ts_ns,
            limit=limit,
            event_count=0,
            checksum_run1="",
            checksum_run2="",
            deterministic=False,
            detail=f"import_error: {exc}",
        )

    reconstructor = get_ledger_reconstructor()
    try:
        r1 = reconstructor.reconstruct(
            stream_kind=stream_kind,
            since_ts_ns=since_ts_ns,
            until_ts_ns=until_ts_ns,
            limit=limit,
            ts_ns=ts_ns,
        )
        r2 = reconstructor.reconstruct(
            stream_kind=stream_kind,
            since_ts_ns=since_ts_ns,
            until_ts_ns=until_ts_ns,
            limit=limit,
            ts_ns=ts_ns,
        )
    except Exception as exc:
        return ValidationResult(
            stream_kind=stream_kind,
            since_ts_ns=since_ts_ns,
            limit=limit,
            event_count=0,
            checksum_run1="",
            checksum_run2="",
            deterministic=False,
            detail=f"reconstruction_error: {exc}",
        )

    deterministic = r1.checksum == r2.checksum
    detail = "OK" if deterministic else f"DIVERGED run1={r1.checksum!r} run2={r2.checksum!r}"

    return ValidationResult(
        stream_kind=stream_kind,
        since_ts_ns=since_ts_ns,
        limit=limit,
        event_count=r1.event_count,
        checksum_run1=r1.checksum,
        checksum_run2=r2.checksum,
        deterministic=deterministic,
        detail=detail,
    )


def validate_all_streams(ts_ns: int = 0) -> dict[str, ValidationResult]:
    """Validate replay determinism for all canonical stream kinds."""
    streams = ["MARKET", "SYSTEM", "GOVERNANCE", "HAZARD", "AUTHORITY"]
    return {s: validate_replay(s, ts_ns=ts_ns) for s in streams}


def print_result(result: ValidationResult) -> None:
    status = "PASS" if result.deterministic else "FAIL"
    print(f"[{status}] stream={result.stream_kind} events={result.event_count} "
          f"checksum={result.checksum_run1[:12]}... detail={result.detail}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate ledger replay determinism (INV-15)")
    parser.add_argument("--stream", default="SYSTEM",
                        help="Ledger stream kind to validate (default: SYSTEM)")
    parser.add_argument("--since", type=int, default=0,
                        help="since_ts_ns lower bound (default: 0)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Maximum events to replay")
    parser.add_argument("--all", action="store_true",
                        help="Validate all canonical streams")
    args = parser.parse_args()

    import time
    ts_ns = time.time_ns()

    if args.all:
        results = validate_all_streams(ts_ns=ts_ns)
        all_pass = True
        for stream, result in results.items():
            print_result(result)
            if not result.deterministic:
                all_pass = False
        sys.exit(0 if all_pass else 1)
    else:
        result = validate_replay(
            stream_kind=args.stream,
            since_ts_ns=args.since,
            limit=args.limit,
            ts_ns=ts_ns,
        )
        print_result(result)
        if not result.deterministic:
            sys.exit(1)
        if result.detail.startswith("import_error") or result.detail.startswith("reconstruction_error"):
            sys.exit(2)


if __name__ == "__main__":
    main()


__all__ = ["ValidationResult", "validate_all_streams", "validate_replay"]
