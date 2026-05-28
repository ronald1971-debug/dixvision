"""Alpha Miner — discovers unknown trading edges.

Searches for:
- Feature importance shifts (what used to not matter now matters)
- Correlation breaks (historical correlations breaking down)
- Anomaly alpha (unusual patterns that precede moves)
- Signal decay detection (existing signals losing power)
- Latent factor emergence (new market drivers appearing)

This is the system's "curiosity" — actively hunting for new edges
rather than waiting for them to be manually discovered.
"""

from intelligence_engine.alpha_miner.anomaly_detector import (
    AnomalyAlphaDetector,
    AnomalySignal,
)
from intelligence_engine.alpha_miner.correlation_monitor import (
    CorrelationBreak,
    CorrelationMonitor,
)
from intelligence_engine.alpha_miner.feature_discoverer import (
    DiscoveredFeature,
    FeatureDiscoverer,
)

__all__ = [
    "FeatureDiscoverer",
    "DiscoveredFeature",
    "CorrelationMonitor",
    "CorrelationBreak",
    "AnomalyAlphaDetector",
    "AnomalySignal",
]
