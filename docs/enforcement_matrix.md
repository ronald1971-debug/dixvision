# DIX v42.2 — Enforcement Matrix

Maps each constraint (INV-*/B-*/FAIL-*) to its enforcement mechanism:
test, YAML guard, code assertion, or review gate.

---

## Legend

| Level | Meaning |
|-------|---------|
| **AUTO** | Enforced automatically by CI test |
| **YAML** | Enforced by schema/value in a registry YAML |
| **CODE** | Enforced by runtime assertion or type system |
| **REVIEW** | Enforced by PR review gate (no automated check) |
| **DRIFT-KILLER** | Enforced by a dedicated `tests/drift_killers/` test |

---

## Invariant Enforcement

| ID | Constraint | Level | Enforcement File |
|----|-----------|-------|-----------------|
| INV-08 | Four canonical event types only | CODE | `core/event_types.py` — EventKind enum with exactly 4 members |
| INV-15 | Byte-identical replay | DRIFT-KILLER | `tests/drift_killers/test_replay_gate.py` |
| INV-15 | No wall-clock reads in pure modules | DRIFT-KILLER | `tests/drift_killers/test_no_hidden_channels.py` |
| INV-48 | Fallback lane budget ≤ 1ms | YAML + CODE | `registry/meta_controller.yaml` → `execution/event_emitter.py` |
| INV-49 | Regime hysteresis thresholds | YAML | `registry/regime_hysteresis.yaml` |
| INV-52 | Shadow MetaController non-acting | CODE | `governance_engine/services/patch_pipeline.py` stage guard |
| INV-53 | Calibration loop offline-only | YAML + CODE | `registry/calibration.yaml` + `triple_window_dry_run.py` |
| INV-55 | Calibration changes governance-gated | CODE + REVIEW | `patch_pipeline.py` PatchStage gate |
| INV-71 | No SignalEvent/ExecutionEvent construction in transport | CODE + DRIFT-KILLER | `tests/drift_killers/test_no_hidden_channels.py` |

---

## Build Directive Enforcement

| ID | Directive | Level | Enforcement File |
|----|-----------|-------|-----------------|
| B1 | No engine cross-imports in transport | DRIFT-KILLER | `tests/drift_killers/test_no_hidden_channels.py` |
| B15 | Agent context key allowlist | YAML | `registry/agent_context_keys.yaml` |
| B18 | Reward component allowlist | YAML | `registry/reward_components.yaml` |
| B27 | No SignalEvent construction in transport | CODE | `execution/async_bus.py`, `lifecycle_emitter.py` |
| B28 | No ExecutionEvent construction in transport | CODE | `execution/async_bus.py`, `lifecycle_emitter.py` |

---

## Failure Mode Enforcement

| ID | Failure Mode | Level | Enforcement File |
|----|-------------|-------|-----------------|
| FAIL-16 | Boot integrity failure halts system | CODE | `integrity/verify_boot.py` — raises RuntimeError |

---

## Snapshot / Dataclass Enforcement

| Constraint | Level | Enforcement File |
|-----------|-------|-----------------|
| All value objects frozen=True | DRIFT-KILLER | `tests/drift_killers/test_snapshot_boundary.py` |
| All value objects slots=True | DRIFT-KILLER | `tests/drift_killers/test_snapshot_boundary.py` |

---

## Registry Structural Enforcement

| File | Required Keys | Level | Enforcement File |
|------|--------------|-------|-----------------|
| `strategies/definitions.yaml` | `strategies` | AUTO | `tests/drift_killers/test_registry_lock.py` |
| `strategies/lifecycle.yaml` | `states`, `valid_transitions` | AUTO | `tests/drift_killers/test_registry_lock.py` |
| `agent_context_keys.yaml` | `allowed_keys` | AUTO | `tests/drift_killers/test_registry_lock.py` |
| `regime_hysteresis.yaml` | `persistence_ticks`, `confidence_delta` | AUTO | `tests/drift_killers/test_registry_lock.py` |
| `reward_components.yaml` | `allowed_components` | AUTO | `tests/drift_killers/test_registry_lock.py` |
| `calibration.yaml` | `window_ns`, `thresholds` | AUTO | `tests/drift_killers/test_registry_lock.py` |
| `meta_controller.yaml` | `shadow_policy`, `fallback_lane` | AUTO | `tests/drift_killers/test_registry_lock.py` |

---

## Behavior Regression Enforcement

| Test | Covers | Level |
|------|--------|-------|
| `test_behavior_diff.py` | Golden numeric outputs for impact model, TWAP, adversarial executor | AUTO |
| `test_replay_gate.py` | Determinism of all pure-computation modules | AUTO |

---

## Gaps (REVIEW-only, no automated enforcement)

The following constraints rely solely on PR review and have no automated test:

- **B27/B28 completeness**: Only checked for known transport modules; new transport modules added without tests would bypass the check.
- **INV-55 governance gate**: The patch pipeline enforces stage gating, but the governance body approval step is a human process.
- **INV-52 shadow non-acting**: Checked in `patch_pipeline.py` but no isolated unit test for the shadow MetaController path.

*Address these gaps by adding targeted tests when the subsystems stabilise.*

---

*Last updated: 2026-05-28*
