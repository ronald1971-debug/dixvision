"""Trader discovery pipeline (Sensory-S1.D — Tier 4.4).

Discovers active traders across platforms (X/Twitter, TradingView,
YouTube, Substack) and builds initial profiles for monitoring.

__capability_tier__ = 0
__forbidden_tiers__ = (5,)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__capability_tier__ = 0
__forbidden_tiers__ = (5,)


class DiscoveryPlatform(StrEnum):
    """Platforms for trader discovery."""

    X_TWITTER = "x_twitter"
    TRADINGVIEW = "tradingview"
    YOUTUBE = "youtube"
    SUBSTACK = "substack"
    TELEGRAM = "telegram"
    DISCORD = "discord"


class TraderTier(StrEnum):
    """Classification tier for discovered traders."""

    WHALE = "whale"  # large capital, high conviction
    PROFESSIONAL = "professional"  # full-time, consistent
    SEMI_PRO = "semi_pro"  # part-time, above average
    RETAIL = "retail"  # occasional, average
    BOT = "bot"  # automated/algorithmic
    NOISE = "noise"  # spam/shill accounts


@dataclass(frozen=True, slots=True)
class DiscoveredTrader:
    """A newly discovered trader profile."""

    platform_id: str
    platform: DiscoveryPlatform
    display_name: str
    follower_count: int
    post_frequency: float  # posts per day
    focus_assets: tuple[str, ...]
    estimated_tier: TraderTier
    first_seen_ts_ns: int
    credibility_signals: int  # count of positive signals


@dataclass(slots=True)
class DiscoveryConfig:
    """Configuration for the discovery pipeline."""

    platforms: tuple[DiscoveryPlatform, ...] = (
        DiscoveryPlatform.X_TWITTER,
        DiscoveryPlatform.TRADINGVIEW,
    )
    min_follower_count: int = 1000
    min_post_frequency: float = 0.5  # at least 1 post every 2 days
    focus_assets: tuple[str, ...] = ("BTC", "ETH", "SOL")
    max_discovery_per_run: int = 50
    exclude_tiers: tuple[TraderTier, ...] = (TraderTier.NOISE, TraderTier.BOT)


class TraderDiscoveryEngine:
    """Discovers traders from web sources.

    Uses Playwright-backed crawling (via sensory/web_autolearn)
    to find and classify active traders.
    """

    def __init__(self, *, config: DiscoveryConfig | None = None) -> None:
        self._config = config or DiscoveryConfig()
        self._discovered: list[DiscoveredTrader] = []
        self._seen_ids: set[str] = set()

    def discover(self, *, ts_ns: int = 0) -> list[DiscoveredTrader]:
        """Run a discovery cycle.

        In production: calls Playwright crawler → extracts profiles.
        Returns newly discovered traders (not previously seen).
        """
        # Production placeholder — actual implementation would
        # invoke crawler_playwright with trader-focused seeds
        return []

    def add_discovered(self, trader: DiscoveredTrader) -> bool:
        """Manually add a discovered trader (from webhook or manual entry)."""
        if trader.platform_id in self._seen_ids:
            return False
        if trader.estimated_tier in self._config.exclude_tiers:
            return False
        self._seen_ids.add(trader.platform_id)
        self._discovered.append(trader)
        return True

    @property
    def total_discovered(self) -> int:
        """Total unique traders discovered."""
        return len(self._discovered)

    @property
    def discovered_traders(self) -> list[DiscoveredTrader]:
        """All discovered traders."""
        return list(self._discovered)
