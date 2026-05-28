"""tools/config_validator.py
DIX VISION v42.2 — Registry Configuration Validator

Validates all registry YAML files against their required schema:
checks for required top-level keys, type correctness, and cross-file
referential integrity (e.g., strategy IDs referenced in performance.yaml
must exist in definitions.yaml).

Usage:
    python tools/config_validator.py [--registry-path PATH] [--strict]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).parents[1]
_REGISTRY = _ROOT / "registry"


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError("pyyaml required: pip install pyyaml") from exc
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# Schema: mapping of rel-path → {required_keys: [...], type_checks: {key: type}}
_SCHEMAS: dict[str, dict[str, Any]] = {
    "strategies/definitions.yaml": {
        "required": ["strategies"],
        "type_checks": {"strategies": list},
    },
    "strategies/lifecycle.yaml": {
        "required": ["lifecycle_states"],
        "type_checks": {"lifecycle_states": list},
    },
    "strategies/performance.yaml": {
        "required": ["performance"],
        "type_checks": {"performance": list},
    },
    "agent_context_keys.yaml": {
        "required": ["allowlist"],
        "type_checks": {"allowlist": list},
    },
    "regime_hysteresis.yaml": {
        "required": ["hysteresis"],
        "type_checks": {"hysteresis": dict},
    },
    "reward_components.yaml": {
        "required": ["components"],
        "type_checks": {"components": list},
    },
    "calibration.yaml": {
        "required": ["coherence_calibrator"],
        "type_checks": {"coherence_calibrator": dict},
    },
    "meta_controller.yaml": {
        "required": ["shadow_policy", "fallback_lane"],
        "type_checks": {"shadow_policy": dict, "fallback_lane": dict},
    },
    "risk.yaml": {
        "required": [],
    },
    "layers.yaml": {
        "required": [],
    },
    "enforcement_policies.yaml": {
        "required": [],
    },
    "governance_ruleset.yaml": {
        "required": [],
    },
    "alerts.yaml": {
        "required": [],
    },
    "budgets.yaml": {
        "required": [],
    },
    "agents.yaml": {
        "required": [],
    },
    "feature_flags.yaml": {
        "required": [],
    },
}


class ValidationError:
    def __init__(self, file: str, message: str) -> None:
        self.file = file
        self.message = message

    def __str__(self) -> str:
        return f"  [{self.file}] {self.message}"


def validate_file(
    rel_path: str,
    schema: dict[str, Any],
    registry_root: Path,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    full = registry_root / rel_path
    if not full.exists():
        errors.append(ValidationError(rel_path, "FILE MISSING"))
        return errors
    try:
        data = _load_yaml(full)
    except Exception as exc:  # noqa: BLE001
        errors.append(ValidationError(rel_path, f"PARSE ERROR: {exc}"))
        return errors

    for key in schema.get("required", []):
        if key not in data:
            errors.append(ValidationError(rel_path, f"missing required key: {key!r}"))

    for key, expected_type in schema.get("type_checks", {}).items():
        if key in data and not isinstance(data[key], expected_type):
            errors.append(ValidationError(
                rel_path,
                f"key {key!r}: expected {expected_type.__name__}, "
                f"got {type(data[key]).__name__}",
            ))
    return errors


def validate_cross_refs(registry_root: Path) -> list[ValidationError]:
    errors: list[ValidationError] = []
    defs_path = registry_root / "strategies/definitions.yaml"
    perf_path = registry_root / "strategies/performance.yaml"
    if not defs_path.exists() or not perf_path.exists():
        return errors
    try:
        defs = _load_yaml(defs_path)
        perf = _load_yaml(perf_path)
    except Exception:  # noqa: BLE001
        return errors

    defined_ids = {s.get("id") for s in defs.get("strategies", []) if isinstance(s, dict)}
    perf_ids = {p.get("id") for p in perf.get("performance", []) if isinstance(p, dict)}
    orphaned = perf_ids - defined_ids - {None}
    for oid in sorted(orphaned):
        errors.append(ValidationError(
            "strategies/performance.yaml",
            f"strategy {oid!r} in performance.yaml not found in definitions.yaml",
        ))
    return errors


def run_validation(registry_root: Path, strict: bool = False) -> int:
    all_errors: list[ValidationError] = []
    print(f"Validating registry at: {registry_root}")
    for rel_path, schema in _SCHEMAS.items():
        errs = validate_file(rel_path, schema, registry_root)
        all_errors.extend(errs)

    cross_errs = validate_cross_refs(registry_root)
    all_errors.extend(cross_errs)

    if all_errors:
        print(f"\n{len(all_errors)} validation error(s):")
        for err in all_errors:
            print(err)
        return 1

    file_count = sum(1 for r in _SCHEMAS if (registry_root / r).exists())
    print(f"All {file_count} checked registry files valid.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="DIX registry config validator")
    parser.add_argument("--registry-path", type=Path, default=_REGISTRY)
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 on missing optional files")
    args = parser.parse_args()
    rc = run_validation(args.registry_path, strict=args.strict)
    sys.exit(rc)


if __name__ == "__main__":
    main()
