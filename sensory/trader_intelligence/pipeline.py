"""Trader intelligence pipeline orchestrator (Sensory-S1.D — Tier 4.4).

Orchestrates the full pipeline: discovery → monitoring → extraction
→ scoring → integration with trader_modeling.

__capability_tier__ = 0
__forbidden_tiers__ = (5,)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__capability_tier__ = 0
__forbidden_tiers__ = (5,)


class PipelineStage(StrEnum):
    """Pipeline execution stages."""

    IDLE = "idle"
    DISCOVERY = "discovery"
    MONITORING = "monitoring"
    EXTRACTION = "extraction"
    SCORING = "scoring"
    INTEGRATION = "integration"


class PipelineHealth(StrEnum):
    """Pipeline health states."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"  # some stages failing
    OFFLINE = "offline"


@dataclass(slots=True)
class PipelineStats:
    """Running statistics for the pipeline."""

    total_runs: int = 0
    total_discovered: int = 0
    total_signals_extracted: int = 0
    total_scores_computed: int = 0
    total_integrations: int = 0
    last_run_ts_ns: int = 0
    avg_run_duration_ms: float = 0.0
    error_count: int = 0


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Configuration for the full pipeline."""

    discovery_interval_ns: int = 3_600_000_000_000  # 1 hour
    monitoring_interval_ns: int = 300_000_000_000  # 5 minutes
    scoring_interval_ns: int = 86_400_000_000_000  # 1 day
    max_tracked_traders: int = 200
    min_score_threshold: float = 0.3
    auto_integrate: bool = True


class TraderIntelligencePipeline:
    """Orchestrates the complete trader intelligence pipeline.

    Stages:
    1. Discovery — find new traders (hourly)
    2. Monitoring — check tracked traders (every 5 min)
    3. Extraction — parse content for signals
    4. Scoring — compute reliability scores (daily)
    5. Integration — feed to trader_modeling (continuous)
    """

    def __init__(self, *, config: PipelineConfig | None = None) -> None:
        self._config = config or PipelineConfig()
        self._stage = PipelineStage.IDLE
        self._health = PipelineHealth.HEALTHY
        self._stats = PipelineStats()
        self._tracked_traders: set[str] = set()

    @property
    def stage(self) -> PipelineStage:
        """Current pipeline stage."""
        return self._stage

    @property
    def health(self) -> PipelineHealth:
        """Current pipeline health."""
        return self._health

    @property
    def stats(self) -> PipelineStats:
        """Pipeline statistics."""
        return self._stats

    @property
    def tracked_count(self) -> int:
        """Number of traders being tracked."""
        return len(self._tracked_traders)

    def should_run_discovery(self, *, current_ts_ns: int) -> bool:
        """Check if discovery cycle is due."""
        if self._stats.last_run_ts_ns == 0:
            return True
        return current_ts_ns - self._stats.last_run_ts_ns >= self._config.discovery_interval_ns

    def run_cycle(self, *, ts_ns: int = 0) -> PipelineStats:
        """Run one full pipeline cycle.

        In production: calls discovery → monitor → extract → score → integrate.
        Returns updated stats.
        """
        self._stage = PipelineStage.DISCOVERY
        # Discovery phase (placeholder)
        self._stage = PipelineStage.MONITORING
        # Monitoring phase (placeholder)
        self._stage = PipelineStage.EXTRACTION
        # Extraction phase (placeholder)
        self._stage = PipelineStage.SCORING
        # Scoring phase (placeholder)
        self._stage = PipelineStage.INTEGRATION
        # Integration phase (placeholder)

        self._stats.total_runs += 1
        self._stats.last_run_ts_ns = ts_ns
        self._stage = PipelineStage.IDLE
        return self._stats

    def add_trader(self, trader_id: str) -> bool:
        """Add a trader to tracking."""
        if len(self._tracked_traders) >= self._config.max_tracked_traders:
            return False
        self._tracked_traders.add(trader_id)
        return True

    def remove_trader(self, trader_id: str) -> None:
        """Remove a trader from tracking."""
        self._tracked_traders.discard(trader_id)
