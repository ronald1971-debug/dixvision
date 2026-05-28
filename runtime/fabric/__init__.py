"""runtime.fabric — Real-Time Execution Fabric (CONVERGENCE PILLAR 2).

Wires existing components (WebSocket feeds, event bus, adapters, fill
handlers) into a coherent async pipeline:

    ingestion → decision → governance → routing → execution → reconciliation → risk

Key properties:
- Async event loop with typed message channels
- Backpressure via bounded queues
- Deterministic replay support (all stages take ts_ns)
- Failure isolation (stage failure → hazard event, not crash)
"""
