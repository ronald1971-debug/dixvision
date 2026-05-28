"""mind — INDIRA market intelligence + fast-path decision engine.

LEGACY: This package is the pre-convergence intelligence layer. The
canonical intelligence engine lives in ``intelligence_engine/``. New
code should import from ``intelligence_engine`` instead. This package
is retained for backward compatibility and will be removed in a future
major version.
"""

from .engine import ExecutionEvent, IndiraEngine
from .intent_producer import IndiraIntent, IntentProducer, IntentType

__all__ = [
    "IndiraEngine",
    "ExecutionEvent",
    "IntentProducer",
    "IndiraIntent",
    "IntentType",
]
