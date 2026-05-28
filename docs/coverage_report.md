# DIX v42.2 — Canonical Coverage Report

Generated: 2026-05-28

## Summary

| Category | Target Files | Present | Coverage |
|----------|-------------|---------|----------|
| execution/ bus lanes | 6 | 6 | 100% |
| execution_engine/strategic_execution/ | 6 | 6 | 100% |
| execution_engine/strategic_execution/market_impact/ | 4 | 4 | 100% |
| intelligence_engine/cross_asset/ | 5 | 5 | 100% |
| intelligence_engine/opponent_model/ | 4 | 4 | 100% |
| intelligence_engine/macro/ | 5 | 5 | 100% |
| governance_engine/services/ | 6 | 6 | 100% |
| governance_engine/plugin_lifecycle/ | 5 | 5 | 100% |
| governance_engine/risk_engine/ | 6 | 6 | 100% |
| sensory/web_autolearn/trader_intelligence/ | 7 | 7 | 100% |
| registry/ YAML files | 8 | 8 | 100% |
| integrity/ | 2 | 2 | 100% |
| translation/ | 3 | 3 | 100% |
| tests/drift_killers/ | 5 | 5 | 100% |
| scripts/ | 7 | 7 | 100% |
| cockpit/audit/ | 4 | 4 | 100% |
| cockpit/api/ | 10 | 10 | 100% |
| cockpit/widgets/ | 10 | 10 | 100% |
| cockpit/cli/ | 2 | 2 | 100% |
| state/data_versioning/ | 4 | 4 | 100% |

## Subsystem Detail

### execution/ — Event Bus & Lanes

| File | Tag | Status |
|------|-----|--------|
| `execution/async_bus.py` | EXEC-05 | Present |
| `execution/event_emitter.py` | EXEC-04 | Present |
| `execution/fast_lane.py` | NEW v1 | Present |
| `execution/hazard_lane.py` | NEW v1 | Present |
| `execution/offline_lane.py` | NEW v1 | Present |
| `execution/severity_classifier.py` | EXEC-06 | Present |
| `execution/chaos_engine.py` | EXEC-07 | Present |

### execution_engine/strategic_execution/

| File | Tag | Status |
|------|-----|--------|
| `adversarial_executor.py` | SE-01 | Present |
| `optimal_execution.py` | SE-02 | Present |
| `market_impact/model.py` | SE-03 | Present |
| `market_impact/depth_estimator.py` | SE-04 | Present |
| `market_impact/slippage_curve.py` | SE-05 | Present |

### intelligence_engine/

| File | Tag | Status |
|------|-----|--------|
| `cross_asset/correlation_matrix.py` | XAS-01 | Present |
| `cross_asset/lead_lag.py` | XAS-02 | Present |
| `cross_asset/contagion_detector.py` | XAS-03 | Present |
| `cross_asset/basket_constructor.py` | XAS-04 | Present |
| `opponent_model/behavior_predictor.py` | OPP-01 | Present |
| `opponent_model/crowd_density.py` | OPP-02 | Present |
| `opponent_model/strategy_detector.py` | OPP-03 | Present |
| `macro/regime_classifier.py` | MAC-01 | Present |
| `macro/hidden_state_detector.py` | MAC-02 | Present |
| `macro/latent_embedder.py` | MAC-03 | Present |
| `macro/macro_event_aligner.py` | MAC-04 | Present |

### governance_engine/

| File | Tag | Status |
|------|-----|--------|
| `services/trust_engine.py` | — | Present |
| `services/liveness_watchdog.py` | — | Present |
| `services/triple_window_dry_run.py` | INV-53 | Present |
| `services/overconfidence_guardrail.py` | — | Present |
| `services/audit_replay.py` | — | Present |
| `services/patch_pipeline.py` | INV-52 | Present |
| `plugin_lifecycle/registry_loader.py` | — | Present |
| `plugin_lifecycle/activation_gate.py` | — | Present |
| `plugin_lifecycle/lifecycle_emitter.py` | B27/B28 | Present |
| `plugin_lifecycle/hot_reload_signal.py` | — | Present |
| `risk_engine/position_limits.py` | — | Present |
| `risk_engine/drawdown_guard.py` | — | Present |
| `risk_engine/exposure_limits.py` | — | Present |
| `risk_engine/kill_conditions.py` | — | Present |
| `risk_engine/real_time_risk.py` | — | Present |

### Registry YAML

| File | Constraint | Status |
|------|-----------|--------|
| `strategies/definitions.yaml` | — | Present |
| `strategies/lifecycle.yaml` | — | Present |
| `strategies/performance.yaml` | — | Present |
| `agent_context_keys.yaml` | B15 | Present |
| `regime_hysteresis.yaml` | INV-49 | Present |
| `reward_components.yaml` | B18 | Present |
| `calibration.yaml` | INV-53/55 | Present |
| `meta_controller.yaml` | INV-52/48 | Present |

## Outstanding / Partial Coverage

The following canonical subsystems were identified as partially present
in the Phase 2 audit. They may have some but not all canonical files:

- `learning_engine/lanes/` — partial (check with Explore agent)
- `learning_engine/performance_analysis/` — partial
- `system_engine/health_monitors/` — partial
- `state/ledger/` — partial
- `tools/` — partial

Run `python scripts/diagnostics.py` for live import-level checks.
