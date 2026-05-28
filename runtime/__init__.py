"""runtime — Operational Runtime Layer.

This package contains the production runtime components:
- kernel: Deterministic tick loop (main system heartbeat)
- event_fabric: Typed event routing (SYNC governance, ASYNC market)
- reconciliation: State reconciler (authority → subsystem)
- replay_validator: INV-15 determinism verification
- execution_lifecycle: Intent lifecycle tracking
- exchange_connector: Real exchange connection management
- fault_handler: Circuit breakers + auto-degradation
- operational_readiness: Readiness validation for mode transitions
- governance/: Runtime governance enforcement + mode propagation
"""

from __future__ import annotations

__all__: list[str] = []
