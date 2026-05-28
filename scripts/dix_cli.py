"""DIX v42 — unified CLI entry point.

Provides a single command-line interface for diagnostics, verification,
chaos testing, and profiling.

Usage:
    python scripts/dix_cli.py <command> [options]

Commands:
    diag       Run system diagnostics
    verify     Run boot integrity check
    chaos      Run chaos day simulation
    profile    Profile hot path
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))


def cmd_diag(args: argparse.Namespace) -> int:
    import scripts.diagnostics as diag  # noqa: PLC0415
    diag.main()
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    import importlib.util  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location(
        "verify", Path(__file__).parent / "verify.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return 0


def cmd_chaos(args: argparse.Namespace) -> int:
    sys.argv = ["run_chaos_day.py",
                "--seed", str(args.seed),
                "--ticks", str(args.ticks)]
    if args.verbose:
        sys.argv.append("--verbose")
    import importlib.util  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location(
        "run_chaos_day", Path(__file__).parent / "run_chaos_day.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    sys.argv = ["profile_hot_path.py",
                "--n", str(args.n),
                "--iterations", str(args.iterations)]
    import importlib.util  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location(
        "profile_hot_path", Path(__file__).parent / "profile_hot_path.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dix_cli",
        description="DIX v42 command-line interface",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("diag", help="Run system diagnostics")

    verify_p = sub.add_parser("verify", help="Run boot integrity check")
    verify_p.add_argument("--hash-path", type=Path)
    verify_p.add_argument("--core-path", type=Path)
    verify_p.add_argument("--write", action="store_true")

    chaos_p = sub.add_parser("chaos", help="Run chaos day simulation")
    chaos_p.add_argument("--seed", type=int, default=42)
    chaos_p.add_argument("--ticks", type=int, default=1_000)
    chaos_p.add_argument("--verbose", action="store_true")

    profile_p = sub.add_parser("profile", help="Profile hot path")
    profile_p.add_argument("--n", type=int, default=20)
    profile_p.add_argument("--iterations", type=int, default=10_000)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {"diag": cmd_diag, "verify": cmd_verify,
                "chaos": cmd_chaos, "profile": cmd_profile}
    rc = dispatch[args.command](args)
    sys.exit(rc)


if __name__ == "__main__":
    main()
