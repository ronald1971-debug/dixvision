# DIX VISION — Market Cognitive Operating System

## The Reframe

DIX VISION is **not** "an AI trader." It is a **Market Cognitive Operating System (MCOS)** — a platform for controlled adaptability in financial markets.

This distinction changes everything:

| AI Trader | Cognitive OS |
|---|---|
| Maximizes signal extraction | Maximizes controlled adaptability |
| Adds intelligence paths | Compresses authority surfaces |
| Complexity = capability | Compression = reliability |
| System serves the model | System serves the operator |

## Architecture: Compression Model

### The Kernel

```
┌──────────────────────────────────────────────────────┐
│                   SystemKernel                        │
│                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ BeliefState  │  │ System Mode  │  │  Event Bus  │ │
│  │  (regime +   │  │ FSM (PAPER/  │  │ (typed evt  │ │
│  │  market ctx) │  │ CANARY/LIVE) │  │  dispatch)  │ │
│  └─────────────┘  └──────────────┘  └─────────────┘ │
│                                                      │
│  ONE source of truth. All services read from here.   │
└──────────────────────────────────────────────────────┘
```

The kernel owns **exactly three things**:

1. **BeliefState** — the canonical market+regime projection
2. **System Mode FSM** — the canonical mode (PAPER/CANARY/LIVE/AUTO)
3. **Event Bus** — the only path for typed events between services

No service may hold its own authoritative state. No UI widget may read from a local mock. Every component reads from the kernel's immutable snapshot.

### The Signal Funnel

```
┌──────────────────────────────────────────────────────┐
│                Intelligence Services                  │
│                                                      │
│  meta-controller  plugins  cognitive  trader-model   │
│  strategy-runtime neuromorphic  opponent-model       │
│                                                      │
│  ALL emit SignalEvent ──┐                            │
│                         ▼                            │
│              ┌──────────────────┐                    │
│              │   SignalFunnel   │                    │
│              │                  │                    │
│              │  1. Validate     │                    │
│              │  2. Trust-cap    │                    │
│              │  3. Fuse/rank    │                    │
│              │  4. Consensus    │                    │
│              └────────┬─────────┘                    │
│                       ▼                              │
│              FunnelOutput.consensus                   │
│                       │                              │
│                       ▼                              │
│              Execution Gate (INV-68)                  │
└──────────────────────────────────────────────────────┘
```

Every intelligence path — no matter how advanced — must emit `SignalEvent` through the funnel. The funnel:

- **Validates** provenance (registered providers only)
- **Trust-caps** confidence per signal trust level
- **Fuses** signals using tier-weighted scoring
- **Resolves** conflicts (same-symbol, same-tick)
- **Outputs** a single ranked consensus

No path may bypass the funnel to reach execution directly.

### Service Model

```
              SystemKernel
                  │
    ┌─────────────┼─────────────┐
    ▼             ▼             ▼
┌────────┐  ┌────────┐  ┌────────────┐
│ Intel  │  │ Exec   │  │ Governance │
│ Engine │  │ Engine │  │   Engine   │
└────────┘  └────────┘  └────────────┘
    ▲             ▲             ▲
    │             │             │
  service       service       service
  (reads        (reads        (reads
   kernel)       kernel)       kernel)
```

- **Intelligence** = cognition provider (emits signals)
- **Execution** = execution provider (routes intents to venues)
- **Governance** = policy provider (signs/denies intents)
- **System** = health provider (monitors hazards)
- **Learning** = offline feedback provider
- **Evolution** = offline mutation provider

Each is a **service** that registers with the kernel. The kernel dispatches events; services process them and return outputs. No service holds authoritative state.

### UI Binding

```
┌──────────────────────────────────────┐
│          Dashboard Widget            │
│                                      │
│  data = kernel.project()             │
│  # NEVER: data = local_mock()        │
│  # NEVER: data = adapter.cache()     │
│                                      │
│  if not projection.available("X"):   │
│      render("Service X unavailable") │
│  else:                               │
│      render(projection.X_data)       │
└──────────────────────────────────────┘
```

Every widget reads from `StateProjection` (a thin read-only view of the kernel snapshot). If a service isn't available, the widget shows "unavailable" — never mock data.

## Migration Path

### Current State (v42.2)

- `core/kernel.py` — SystemKernel (new, canonical)
- `runtime/kernel.py` — RuntimeKernel (legacy, uses IndiraEngine path)
- `ui/server.py._State` — god-object (legacy, holds mixed state)
- `runtime/authority.py` — RuntimeAuthorityStore (legacy, partial state)

### Target State (v43) — ACHIEVED

- `core/kernel.py` — SystemKernel is the ONLY state authority ✅
- `runtime/kernel.py` — delegates canonical state to SystemKernel via authority shim ✅
- `ui/server.py._State` — reads from StateProjection (SystemKernel.project()) ✅
- `runtime/authority.py` — kernel-backed shim, no independent state ✅
- `runtime/authority_bridge.py` — deleted (shim delegates directly) ✅

### Migration Steps

1. ✅ SystemKernel created (`core/kernel.py`)
2. ✅ SignalFunnel created (`intelligence_engine/signal_funnel.py`)
3. ✅ StateProjection created (`ui/state_projection.py`)
4. ✅ Legacy paths marked (decision_pipeline, mind/, execution/, governance/)
5. ✅ `_State` registers all 6 engines with SystemKernel at boot; syncs mode/belief/freeze
6. ✅ `RuntimeKernel` initializes SignalFunnel with registered providers at boot
7. ✅ `/api/kernel/state` endpoint + `/api/health` includes kernel projection; per-tick BeliefState synced from intelligence pipeline
8. ✅ `AuthorityBridge` syncs RuntimeAuthorityStore → SystemKernel; store marked LEGACY
9. ✅ Dashboard widgets migrated to StateProjection: ModeControlBar reads mode from kernel, EngineStatusGrid reads service health from kernel, `/api/health` delegates to kernel, `/api/runtime/status` includes kernel state, dashboard routes overlay kernel projection, SSE stream emits `kernel_state` channel
10. ✅ RuntimeAuthorityStore converted to kernel-backed shim: canonical state (mode, freeze, execution_blocked) delegated to SystemKernel; AuthorityBridge deleted; store no longer holds independent state

## Design Principles

1. **One kernel, one truth** — no service holds authoritative state
2. **Controlled adaptability** — new providers plug in without destabilizing
3. **Composable isolation** — any service can fail without cascading
4. **Operator sovereignty** — kill path never depends on any service
5. **Deterministic replay** — same inputs → same outputs (INV-15)
6. **Compression over complexity** — fewer authority surfaces, stricter contracts
