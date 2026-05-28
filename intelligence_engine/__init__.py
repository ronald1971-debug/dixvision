"""RUNTIME-ENGINE-01 Intelligence (Phase E0 shell).

Owner of all market-intelligence plugins (microstructure, alpha, alt-data,
memory, multi-timeframe, transfer, cognition, agent). Strictly deterministic.

Lint:
- B1 forbids importing from ``execution_engine``, ``system_engine``,
  ``governance_engine``, ``learning_engine``, ``evolution_engine``.
- L3 forbids importing from ``learning_engine`` or ``evolution_engine``.
"""

from intelligence_engine.engine import (
    DEFAULT_SIGNAL_WINDOW_SIZE,
    IntelligenceEngine,
    register_default_providers,
)
from intelligence_engine.runtime_context import RuntimeContext
from intelligence_engine.runtime_context_builder import (
    DEFAULT_LATENCY_BUDGET_NS,
    RuntimeMonitorView,
    build_runtime_context,
)
from intelligence_engine.signal_funnel import (
    FunnelOutput,
    ProviderTier,
    SignalFunnel,
)

__all__ = [
    "DEFAULT_LATENCY_BUDGET_NS",
    "DEFAULT_SIGNAL_WINDOW_SIZE",
    "FunnelOutput",
    "IntelligenceEngine",
    "ProviderTier",
    "RuntimeContext",
    "RuntimeMonitorView",
    "SignalFunnel",
    "build_runtime_context",
    "register_default_providers",
]
