# DIX v42.2 — Total Recall Index

Cross-reference of every system invariant, constraint, and build directive
to the files that implement or enforce them. Keep this index current whenever
new modules are added or invariants are updated.

---

## Invariants (INV-*)

| ID | Invariant | Enforced In |
|----|-----------|-------------|
| INV-08 | Four canonical event types only (SIGNAL, EXECUTION, SYSTEM, HAZARD) | `core/event_types.py`, `tests/test_event_contracts.py` |
| INV-15 | Byte-identical replay — pure functions, caller-supplied ts_ns/seed | all `pure/` modules, `tests/drift_killers/test_replay_gate.py` |
| INV-48 | MetaController fallback lane budget ≤ 1ms | `execution/event_emitter.py`, `registry/meta_controller.yaml` |
| INV-49 | Regime hysteresis — persistence_ticks=3, confidence_delta=0.08 | `registry/regime_hysteresis.yaml`, `intelligence_engine/macro/regime_classifier.py` |
| INV-52 | Shadow MetaController non-acting | `governance_engine/services/patch_pipeline.py` |
| INV-53 | Calibration loop offline-only | `registry/calibration.yaml`, `governance_engine/services/triple_window_dry_run.py` |
| INV-55 | Calibration changes governance-gated | `governance_engine/services/patch_pipeline.py`, `registry/calibration.yaml` |
| INV-71 | Never construct SignalEvent/ExecutionEvent in transport modules | `execution/async_bus.py`, `execution/fast_lane.py` |

---

## Build Directives (B*)

| ID | Directive | Enforced In |
|----|-----------|-------------|
| B1 | No engine cross-imports in transport/bus modules | `tests/drift_killers/test_no_hidden_channels.py` |
| B15 | Agent context key allowlist | `registry/agent_context_keys.yaml` |
| B18 | Reward component allowlist | `registry/reward_components.yaml` |
| B27 | Never construct SignalEvent in transport | `execution/async_bus.py`, `execution/event_emitter.py` |
| B28 | Never construct ExecutionEvent in transport | `execution/async_bus.py`, `execution/event_emitter.py` |

---

## Failure Modes (FAIL-*)

| ID | Description | Implementation |
|----|-------------|----------------|
| FAIL-16 | Boot integrity failure → halt | `integrity/verify_boot.py`, `scripts/verify.py` |

---

## Database / Persistence (DB-*)

| ID | Description | Implementation |
|----|-------------|----------------|
| DB-14 | Translation audit write to ledger | `translation/audit_writer.py` |

---

## Execution Engine (EXEC-*)

| ID | Description | Implementation |
|----|-------------|----------------|
| EXEC-04 | Event routing by kind | `execution/event_emitter.py` |
| EXEC-05 | Async bus — background dispatch | `execution/async_bus.py` |
| EXEC-06 | Severity classification — pure | `execution/severity_classifier.py` |
| EXEC-07 | Chaos engine — fault injection | `execution/chaos_engine.py` |

---

## Strategic Execution (SE-*)

| ID | Description | Implementation |
|----|-------------|----------------|
| SE-01 | Adversarial order placement | `execution_engine/strategic_execution/adversarial_executor.py` |
| SE-02 | Optimal execution trajectory (TWAP/AC) | `execution_engine/strategic_execution/optimal_execution.py` |
| SE-03 | Square-root impact model | `execution_engine/strategic_execution/market_impact/model.py` |
| SE-04 | Order-book depth estimator | `execution_engine/strategic_execution/market_impact/depth_estimator.py` |
| SE-05 | Slippage curve builder | `execution_engine/strategic_execution/market_impact/slippage_curve.py` |

---

## Cross-Asset (XAS-*)

| ID | Description | Implementation |
|----|-------------|----------------|
| XAS-01 | Rolling Pearson correlation | `intelligence_engine/cross_asset/correlation_matrix.py` |
| XAS-02 | Lead-lag detection | `intelligence_engine/cross_asset/lead_lag.py` |
| XAS-03 | Contagion detection | `intelligence_engine/cross_asset/contagion_detector.py` |
| XAS-04 | Synthetic basket | `intelligence_engine/cross_asset/basket_constructor.py` |

---

## Macro (MAC-*)

| ID | Description | Implementation |
|----|-------------|----------------|
| MAC-01 | Regime classifier | `intelligence_engine/macro/regime_classifier.py` |
| MAC-02 | Hidden state detector (Wyckoff) | `intelligence_engine/macro/hidden_state_detector.py` |
| MAC-03 | Latent embedder | `intelligence_engine/macro/latent_embedder.py` |
| MAC-04 | Macro event aligner | `intelligence_engine/macro/macro_event_aligner.py` |

---

## Trader Intelligence (TI-ING-*)

| ID | Description | Implementation |
|----|-------------|----------------|
| TI-ING-01 | Source crawler | `sensory/web_autolearn/trader_intelligence/crawler.py` |
| TI-ING-02 | Profile extractor | `sensory/web_autolearn/trader_intelligence/profile_extractor.py` |
| TI-ING-03 | Behavior analyzer | `sensory/web_autolearn/trader_intelligence/behavior_analyzer.py` |
| TI-ING-04 | Performance validator | `sensory/web_autolearn/trader_intelligence/performance_validator.py` |
| TI-ING-05 | Archetype publisher | `sensory/web_autolearn/trader_intelligence/archetype_publisher.py` |

---

## Core (CORE-*)

| ID | Description | Implementation |
|----|-------------|----------------|
| CORE-12 | Boot integrity hash | `integrity/verify_boot.py` |
| CORE-15 | Intent → patch translation | `translation/intent_to_patch.py` |

---

*Last updated: 2026-05-28. Update this index with every new INV/B/FAIL/EXEC/SE code added.*
