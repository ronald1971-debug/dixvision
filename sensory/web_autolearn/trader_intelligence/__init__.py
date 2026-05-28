"""Trader Intelligence Pipeline — structured learning from 5000+ trader sources.

Unified flow: Source Ingestion → Credibility Filter → Content Parsing →
Strategy Extraction → Philosophy Encoding → Abstraction → Validation →
Knowledge Store → Indira Consumption.

All data flows through ``sensory → learning → validated → registry``
per authority lint quarantine (C3 / SAFE-15).
"""

from __future__ import annotations

from sensory.web_autolearn.trader_intelligence.contracts import (
    SourceCategory,
    TraderPattern,
    TraderSource,
)
from sensory.web_autolearn.trader_intelligence.pipeline import (
    TraderIntelligencePipeline,
)

__all__ = [
    "SourceCategory",
    "TraderIntelligencePipeline",
    "TraderPattern",
    "TraderSource",
]
