"""mind.risk_cache — Hot-Path Risk Cache for Mind Module.

Re-exports the canonical FastRiskCache from system.fast_risk_cache for
backward compatibility. The mind module uses this to access precomputed
risk thresholds without I/O on the hot path.

The risk cache is written by governance_engine and read by all hot-path
modules (L1 oracle, execution gate, intelligence evaluators).
"""

from __future__ import annotations

from system.fast_risk_cache import FastRiskCache, get_risk_cache

__all__ = ["FastRiskCache", "get_risk_cache"]
