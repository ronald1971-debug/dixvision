"""execution — Trade execution + emergency execution domain.

LEGACY: This package is the pre-convergence execution layer. The
canonical execution engine lives in ``execution_engine/``. New code
should import from ``execution_engine`` instead. This package is
retained for backward compatibility and will be removed in a future
major version.

Canonical split:
  Indira (market) → ``trade_executor`` → adapters
  Hazard      → ``emergency_executor`` → mode transitions / kill switch

Dyon system maintenance lives under the same package but CANNOT touch
adapters or the trade_executor.
"""

from .engine import DyonEngine, get_dyon_engine

__all__ = ["DyonEngine", "get_dyon_engine"]
