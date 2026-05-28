"""tools/enforcement_matrix.py
DIX VISION v42.2 — Enforcement Matrix Generator

Scans the codebase to verify that every INV-*/B-*/FAIL-* constraint
has an associated test file or runtime assertion. Outputs a table
showing enforcement status for each known constraint.

Usage:
    python tools/enforcement_matrix.py [--output {text,json}]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).parents[1]

# Canonical constraints and their expected enforcement locations
_CONSTRAINTS: list[dict] = [
    {"id": "INV-08", "description": "Four canonical event types only",
     "expected_files": ["core/contracts/events.py"]},
    {"id": "INV-15", "description": "Byte-identical replay",
     "expected_files": ["tests/drift_killers/test_replay_gate.py"]},
    {"id": "INV-48", "description": "MetaController fallback lane <=1ms",
     "expected_files": ["registry/meta_controller.yaml", "execution/event_emitter.py"]},
    {"id": "INV-49", "description": "Regime hysteresis thresholds",
     "expected_files": ["registry/regime_hysteresis.yaml"]},
    {"id": "INV-52", "description": "Shadow MetaController non-acting",
     "expected_files": ["governance_engine/services/patch_pipeline.py"]},
    {"id": "INV-53", "description": "Calibration loop offline-only",
     "expected_files": ["registry/calibration.yaml"]},
    {"id": "INV-55", "description": "Calibration changes governance-gated",
     "expected_files": ["governance_engine/services/patch_pipeline.py"]},
    {"id": "INV-71", "description": "No SignalEvent/ExecutionEvent in transport",
     "expected_files": ["tests/drift_killers/test_no_hidden_channels.py"]},
    {"id": "B1", "description": "No engine cross-imports in transport",
     "expected_files": ["tests/drift_killers/test_no_hidden_channels.py"]},
    {"id": "B15", "description": "Agent context key allowlist",
     "expected_files": ["registry/agent_context_keys.yaml"]},
    {"id": "B18", "description": "Reward component allowlist",
     "expected_files": ["registry/reward_components.yaml"]},
    {"id": "B27", "description": "No SignalEvent in transport",
     "expected_files": ["execution/async_bus.py"]},
    {"id": "B28", "description": "No ExecutionEvent in transport",
     "expected_files": ["execution/async_bus.py"]},
    {"id": "FAIL-16", "description": "Boot integrity failure halts system",
     "expected_files": ["integrity/verify_boot.py"]},
]


@dataclass
class MatrixRow:
    constraint_id: str
    description: str
    enforcement_files: list[str]
    present: list[str]
    missing: list[str]

    @property
    def status(self) -> str:
        if not self.missing:
            return "ENFORCED"
        if not self.present:
            return "MISSING"
        return "PARTIAL"


def build_matrix() -> list[MatrixRow]:
    rows: list[MatrixRow] = []
    for c in _CONSTRAINTS:
        present = []
        missing = []
        for rel in c["expected_files"]:
            path = _ROOT / rel
            if path.exists():
                present.append(rel)
            else:
                missing.append(rel)
        rows.append(MatrixRow(
            constraint_id=c["id"],
            description=c["description"],
            enforcement_files=c["expected_files"],
            present=present,
            missing=missing,
        ))
    return rows


def scan_for_references(constraint_id: str) -> list[str]:
    results: list[str] = []
    pattern = constraint_id.replace("-", r"[-_]?")
    try:
        import subprocess  # noqa: PLC0415
        result = subprocess.run(
            ["grep", "-rl", "--include=*.py", constraint_id, str(_ROOT)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                rel = str(Path(line).relative_to(_ROOT))
                if ".claude" not in rel and "__pycache__" not in rel:
                    results.append(rel)
    except Exception:  # noqa: BLE001
        pass
    return results[:5]


def print_text_report(rows: list[MatrixRow]) -> None:
    import sys  # noqa: PLC0415
    if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
        import io  # noqa: PLC0415
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    enforced = sum(1 for r in rows if r.status == "ENFORCED")
    partial = sum(1 for r in rows if r.status == "PARTIAL")
    missing_count = sum(1 for r in rows if r.status == "MISSING")

    print(f"DIX v42.2 Enforcement Matrix - {len(rows)} constraints")
    print(f"  ENFORCED: {enforced}  PARTIAL: {partial}  MISSING: {missing_count}")
    print()

    col_id = 10
    col_desc = 42
    col_status = 10
    header = f"{'ID':<{col_id}} {'Description':<{col_desc}} {'Status':<{col_status}}"
    print(header)
    print("-" * len(header))
    for row in rows:
        status_sym = {"ENFORCED": "OK", "PARTIAL": "~~", "MISSING": "XX"}.get(row.status, "?")
        print(f"{row.constraint_id:<{col_id}} {row.description:<{col_desc}} "
              f"{status_sym} {row.status}")
        for m in row.missing:
            print(f"  {'':>{col_id}}   MISSING: {m}")


def print_json_report(rows: list[MatrixRow]) -> None:
    data = [
        {
            "id": r.constraint_id,
            "description": r.description,
            "status": r.status,
            "present": r.present,
            "missing": r.missing,
        }
        for r in rows
    ]
    print(json.dumps(data, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="DIX enforcement matrix generator")
    parser.add_argument("--output", choices=["text", "json"], default="text")
    args = parser.parse_args()

    rows = build_matrix()
    if args.output == "json":
        print_json_report(rows)
    else:
        print_text_report(rows)

    missing_count = sum(1 for r in rows if r.status == "MISSING")
    sys.exit(0 if missing_count == 0 else 1)


if __name__ == "__main__":
    main()
