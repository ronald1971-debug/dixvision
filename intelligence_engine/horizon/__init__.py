"""Multi-Horizon Engine — temporal intelligence fusion.

Cutting-edge systems think simultaneously in:
- Microseconds (HFT layer)
- Seconds (scalping layer)
- Minutes (intraday layer)
- Hours-Days (swing layer)
- Weeks-Months (macro layer)

Each horizon has its own signal generation, but they must agree
or conflict must be resolved. The engine fuses multi-scale signals
into a unified view.
"""

from intelligence_engine.horizon.horizon_engine import (
    FusedSignal,
    HorizonEngine,
    HorizonLayer,
    TimeHorizon,
)

__all__ = [
    "HorizonEngine",
    "HorizonLayer",
    "TimeHorizon",
    "FusedSignal",
]
