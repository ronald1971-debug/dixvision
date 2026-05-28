# DIX VISION v42.2 — Convergence Implementation Plan

## Executive Summary

Four pillars transform DIX from architectural framework → production-capable trading system.
Each pillar depends on the prior. Total: ~45 new/extended files across 4 PRs.

---

## PILLAR 1: Unified Runtime Authority

**Problem**: State is scattered across 3+ locations:
- `system/state.py` — `StateManager` with `SystemState` (mode, health, drawdown)
- `system_engine/state/system_state.py` — `SystemState` with hazards/heartbeats
- `ui/server.py` — `STATE` object (dashboard-local: positions, orders, learning_override)
- `core/contracts/operator_authority.py` — `OperatorAuthority` (new from build-directive)

Each subsystem reads its own local truth. No single authoritative runtime snapshot.

**Solution**: Create `runtime/authority.py` — the **single point of truth** that all subsystems read from and only designated writers (governance, operator bridge) may write to.

### Files

| File | Action | Description |
|------|--------|-------------|
| `runtime/__init__.py` | CREATE | Package init |
| `runtime/authority.py` | CREATE | `RuntimeAuthority` — single frozen snapshot class + `RuntimeAuthorityStore` (read-many, write-few) |
| `runtime/projections.py` | CREATE | Read-only projections: `market_projection()`, `execution_projection()`, `governance_projection()` |
| `runtime/writer.py` | CREATE | `AuthorityWriter` — only governance + operator_bridge may call. Emits change events to ledger. |
| `runtime/subscriptions.py` | CREATE | Reactive subscription model — subsystems subscribe to slices of state |
| `tools/authority_lint.py` | EXTEND | B-RUNTIME rule: only `runtime/writer.py` may mutate `RuntimeAuthorityStore` |

### Key Design Decisions

1. **Single frozen snapshot per tick** — `RuntimeSnapshot` is a `@dataclass(frozen=True, slots=True)` capturing all state axes at one `ts_ns`
2. **Monotonic version counter** — every write increments version; readers can detect stale cache
3. **Projection-based reads** — subsystems get typed projections (not raw state) to enforce separation of concerns
4. **Writer protocol** — only holders of a `WriterToken` (issued to governance_engine + operator_interface_bridge) may update state
5. **Ledger integration** — every state transition → SystemEvent → ledger row (audit trail)

### RuntimeSnapshot Schema

```python
@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    version: int
    ts_ns: int
    # Operator authority (from build-directive)
    operator_authority: OperatorAuthority
    # System mode (FSM state)
    system_mode: str  # LOCKED/SAFE/PAPER/CANARY/LIVE/AUTO
    # Health
    health_score: float
    active_hazards: tuple[str, ...]
    # Execution state
    live_execution_blocked: bool
    open_positions: int
    total_exposure_usd: float
    # Market state
    last_market_ts_ns: int
    # Governance
    governance_mode: str
    freeze_active: bool
```

---

## PILLAR 2: Real-Time Execution Fabric

**Problem**: The system has pieces (WebSocket feeds, event bus stubs, adapters) but no unified pipeline from ingestion → decision → execution → reconciliation → risk update.

**Current state**:
- `ui/feeds/binance_public_ws.py` — working WS ingestion (read-only)
- `system_engine/streaming/event_fabric.py` — bytewax-style pipeline (offline only)
- `execution_engine/engine.py` — handles intents but no live loop
- `execution_engine/lifecycle/` — fill handler, order state machine, reconciliation (partial)
- `execution_engine/protections/` — circuit breaker, runtime monitor (exist)

**Solution**: Wire these existing components into a coherent real-time pipeline.

### Files

| File | Action | Description |
|------|--------|-------------|
| `runtime/fabric/__init__.py` | CREATE | Package |
| `runtime/fabric/ingestion_bus.py` | CREATE | Unified ingestion: WS → normalize → RuntimeAuthority update |
| `runtime/fabric/decision_pipeline.py` | CREATE | Market event → intelligence signal → governance check → intent |
| `runtime/fabric/execution_router.py` | CREATE | Intent → route_with_authority → adapter/paper/queue |
| `runtime/fabric/fill_reconciler.py` | CREATE | Fill events → position update → risk snapshot → RuntimeAuthority |
| `runtime/fabric/risk_snapshotter.py` | CREATE | Periodic risk computation → RuntimeAuthority write |
| `runtime/fabric/event_loop.py` | CREATE | Main event loop tying all stages together |
| `execution_engine/lifecycle/fill_handler.py` | EXTEND | Wire into fabric reconciler |
| `execution_engine/protections/reconciliation.py` | EXTEND | Connect to RuntimeAuthority |

### Pipeline Stages (event flow)

```
[WebSocket Feeds] → ingestion_bus → [Normalize] → RuntimeAuthority.market_update()
                                                          ↓
                                              [Intelligence Engine]
                                                          ↓
                                              decision_pipeline (signal)
                                                          ↓
                                              [Governance Gate] ← RuntimeAuthority.read()
                                                          ↓
                                              execution_router (route_with_authority)
                                                    ↓         ↓          ↓
                                              [PAPER]   [QUEUE]    [EXECUTE]
                                                                        ↓
                                                                  [Adapter]
                                                                        ↓
                                                              fill_reconciler
                                                                        ↓
                                                    RuntimeAuthority.position_update()
                                                                        ↓
                                                            risk_snapshotter
                                                                        ↓
                                                    RuntimeAuthority.risk_update()
```

### Key Design Decisions

1. **Async event loop** — `asyncio`-based main loop with typed message channels
2. **Backpressure** — bounded queues between stages; slow consumer triggers circuit breaker
3. **Deterministic replay** — every stage takes `ts_ns` as input (no wall-clock in hot path)
4. **Failure isolation** — stage failure triggers hazard event, does NOT crash pipeline
5. **Metrics emission** — latency/throughput counters at each stage boundary

---

## PILLAR 3: Live Governance Enforcement

**Problem**: Governance currently advises but doesn't block at runtime. The execution gate (`execution_gate.py`) validates intents but governance decisions aren't runtime-blocking in the full pipeline sense.

**Current state**:
- `governance_engine/engine.py` — exists, does approval workflow
- `governance_engine/control_plane/policy_engine.py` — evaluates policies
- `execution_engine/execution_gate.py` — `AuthorityGuard` + `route_with_authority`
- `governance_engine/harness_approver.py` — harness-level approvals

**Solution**: Make governance a **blocking synchronous gate** in the execution fabric. No intent passes without governance's cryptographic signature.

### Files

| File | Action | Description |
|------|--------|-------------|
| `runtime/governance/__init__.py` | CREATE | Package |
| `runtime/governance/enforcement_gate.py` | CREATE | Synchronous blocking gate — call blocks until governance decides |
| `runtime/governance/policy_evaluator.py` | CREATE | Real-time policy evaluation against RuntimeAuthority snapshot |
| `runtime/governance/violation_handler.py` | CREATE | What happens on violation: block, alert, emergency-halt |
| `runtime/governance/deterministic_arbiter.py` | CREATE | Given same inputs → same decision (no randomness, no time-dependence) |
| `governance_engine/control_plane/runtime_enforcer.py` | CREATE | Bridge: governance_engine policies → runtime enforcement |
| `core/contracts/governance_decision.py` | CREATE | Typed decision contract with HMAC signature |

### Enforcement Model

```
Intent arrives at enforcement_gate
  → policy_evaluator.evaluate(intent, runtime_snapshot) → PolicyVerdict
    → ALLOW: sign with HMAC, pass through
    → DENY: block, emit violation, log to ledger
    → CONDITIONAL: block until condition met (e.g., approval queue drain)
  → If intent.governance_signature missing → HARD BLOCK (fail-closed)
  → deterministic_arbiter verifies same input → same output (testable)
```

### Key Design Decisions

1. **Fail-closed** — missing governance signature = blocked (never pass-through on error)
2. **Synchronous in hot path** — governance evaluation completes before execution proceeds
3. **Deterministic** — `deterministic_arbiter` guarantees same RuntimeSnapshot + same Intent → same decision
4. **HMAC-signed decisions** — `GovernanceDecision` carries cryptographic proof of approval
5. **Tiered latency** — fast rules (<1ms) in-process; slow rules (risk models) async with timeout
6. **Emergency override** — operator kill-switch bypasses all governance (logged, audited)

---

## PILLAR 4: Replay Determinism

**Problem**: System can't yet replay an entire session bit-identically. Individual components have determinism (INV-15 in some modules) but no end-to-end replay harness.

**Current state**:
- `simulation/event_replayer.py` — replays event logs (offline)
- `core/time_source.py` — TimeAuthority Protocol (FixedClock, LedgerClock)
- `state/ledger/` — hash-chain, event store, cold store
- Individual modules use `ts_ns` parameters (partial determinism)

**Solution**: Full-system replay that reconstructs market state, decisions, governance, execution, risk, cognition, and learning — given the same ledger log.

### Files

| File | Action | Description |
|------|--------|-------------|
| `runtime/replay/__init__.py` | CREATE | Package |
| `runtime/replay/session_recorder.py` | CREATE | Records all events + state transitions during live session |
| `runtime/replay/session_replayer.py` | CREATE | Given a session recording → reproduce exact state sequence |
| `runtime/replay/determinism_verifier.py` | CREATE | Asserts replayed state == original state at every checkpoint |
| `runtime/replay/clock_injection.py` | CREATE | Injects LedgerClock at all TimeAuthority points during replay |
| `runtime/replay/io_stub.py` | CREATE | Stubs all IO (network, disk) with recorded responses |
| `runtime/replay/divergence_detector.py` | CREATE | Detects and reports first point of divergence |
| `core/contracts/replay_manifest.py` | CREATE | Schema for session recording manifest |

### Replay Architecture

```
[Session Recording]
  ├── events.jsonl        (all bus events in order)
  ├── market_ticks.jsonl  (all ingested market data)
  ├── decisions.jsonl     (all governance decisions)
  ├── executions.jsonl    (all fills/orders)
  ├── state_checkpoints/  (RuntimeSnapshot at each checkpoint)
  └── manifest.json       (metadata, versions, hashes)

[Replay]
  1. Load manifest → validate checksums
  2. Inject LedgerClock(timestamps from events.jsonl)
  3. Stub IO with recorded responses
  4. Create fresh RuntimeAuthority
  5. Feed market_ticks through ingestion_bus
  6. Verify decision_pipeline produces same decisions
  7. Verify execution_router makes same routing choices
  8. At each checkpoint: assert RuntimeSnapshot == recorded snapshot
  9. Report: IDENTICAL / DIVERGED_AT(step_n, expected, actual)
```

### Key Design Decisions

1. **Event-sourced** — the ledger IS the source of truth; state is derived
2. **Checkpoint-based verification** — don't require bit-identity at every ns, verify at stable points
3. **Divergence report** — when replay diverges, report exactly which field, which step, which input caused it
4. **Incremental** — can replay a subset (just decisions, just executions) for targeted debugging
5. **Version-aware** — manifest includes code version; warns if replaying against different code

---

## Implementation Order & PRs

| PR | Pillar | Steps | Dependencies |
|----|--------|-------|--------------|
| PR A | 1: Unified Runtime Authority | `runtime/` core + lint rule | None |
| PR B | 2: Real-Time Execution Fabric | `runtime/fabric/` | PR A (reads RuntimeAuthority) |
| PR C | 3: Live Governance Enforcement | `runtime/governance/` | PR A + B (blocks in fabric) |
| PR D | 4: Replay Determinism | `runtime/replay/` | PR A + B + C (replays full pipeline) |

**Estimated scope**: ~30 new files, ~5 extended files, ~3500 lines of implementation + tests.

---

## Non-Goals (per operator directive)

- No confirmation modals or cooldowns on operator actions
- No autonomous source discovery
- No copy-trading-as-mirror in live execution
- No parallel hierarchy intelligence_engine/trader_intelligence/
- No "safer defaults" that contradict the spec
- No gating of paper/backtest behind anything
