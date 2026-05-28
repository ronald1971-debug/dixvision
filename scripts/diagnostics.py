"""DIX v42 — system diagnostics script.

Checks engine health, registry integrity, and import sanity.
Run with: python scripts/diagnostics.py
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).parents[1]


def _check_import(module: str) -> tuple[str, bool, str]:
    try:
        importlib.import_module(module)
        return (module, True, "ok")
    except ImportError as exc:
        return (module, False, str(exc))
    except Exception as exc:  # noqa: BLE001
        return (module, False, f"ERROR: {exc}")


_CORE_MODULES = [
    "execution.async_bus",
    "execution.fast_lane",
    "execution.hazard_lane",
    "execution.offline_lane",
    "execution.event_emitter",
    "execution.severity_classifier",
    "execution_engine.strategic_execution.adversarial_executor",
    "execution_engine.strategic_execution.optimal_execution",
    "execution_engine.strategic_execution.market_impact.model",
    "intelligence_engine.cross_asset.correlation_matrix",
    "intelligence_engine.macro.regime_classifier",
    "governance_engine.risk_engine.real_time_risk",
]


def check_imports() -> int:
    print("=== Import checks ===")
    failures = 0
    for mod in _CORE_MODULES:
        _, ok, msg = _check_import(mod)
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}] {mod}" + (f" — {msg}" if not ok else ""))
        if not ok:
            failures += 1
    return failures


def check_registry() -> int:
    print("\n=== Registry checks ===")
    registry_dir = _ROOT / "registry"
    required = [
        "strategies/definitions.yaml",
        "strategies/lifecycle.yaml",
        "agent_context_keys.yaml",
        "regime_hysteresis.yaml",
        "reward_components.yaml",
        "calibration.yaml",
        "meta_controller.yaml",
    ]
    failures = 0
    for rel in required:
        path = registry_dir / rel
        status = "OK  " if path.exists() else "MISS"
        print(f"  [{status}] registry/{rel}")
        if not path.exists():
            failures += 1
    return failures


def check_manifest() -> int:
    print("\n=== Manifest check ===")
    manifest = _ROOT / "manifest.md"
    if manifest.exists():
        print(f"  [OK  ] manifest.md ({manifest.stat().st_size} bytes)")
        return 0
    print("  [MISS] manifest.md")
    return 1


def main() -> None:
    sys.path.insert(0, str(_ROOT))
    total_failures = 0
    total_failures += check_imports()
    total_failures += check_registry()
    total_failures += check_manifest()
    print(f"\n{'='*40}")
    if total_failures == 0:
        print("All checks passed.")
    else:
        print(f"{total_failures} check(s) failed.")
    sys.exit(0 if total_failures == 0 else 1)


if __name__ == "__main__":
    main()
