"""GitHub trending repository health monitor.

Monitors GitHub trending repositories for emerging tools and libraries
relevant to the trading system stack. The base implementation is a no-op
stub; subclasses override ``_fetch_trending`` to activate real API calls.

Relevant categories watched by default:
    * ``"algorithmic-trading"``
    * ``"quantitative-finance"``
    * ``"machine-learning"``
    * ``"reinforcement-learning"``

Emits ``SYSTEM/HEALTH_GITHUB_TRENDING`` events to the ledger when
newly discovered relevant repositories are found.
"""

from __future__ import annotations

from state.ledger.event_store import append_event

_DEFAULT_CATEGORIES: tuple[str, ...] = (
    "algorithmic-trading",
    "quantitative-finance",
    "machine-learning",
    "reinforcement-learning",
)


class GithubTrendingMonitor:
    """Monitors GitHub trending repositories for emerging relevant tools.

    The base class keeps the network boundary explicit: no HTTP calls are
    made in ``__init__`` or ``scan``. Subclasses override
    ``_fetch_trending`` to activate real fetching.
    """

    name: str = "github_trending_monitor"
    spec_id: str = "SYS-HEALTH-GHT-01"

    __slots__ = ("_categories", "_last_scan_ts_ns", "_discovered_repos")

    def __init__(
        self,
        categories: tuple[str, ...] | None = None,
    ) -> None:
        self._categories: tuple[str, ...] = (
            categories if categories is not None else _DEFAULT_CATEGORIES
        )
        self._last_scan_ts_ns: int = 0
        # key: repo_full_name → repo dict
        self._discovered_repos: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Fetch hook (override in subclasses / tests)
    # ------------------------------------------------------------------

    def _fetch_trending(self, category: str) -> list[dict]:
        """Fetch trending repositories for a single category.

        Base implementation is a no-op returning an empty list. Override
        this method to activate real GitHub API / scraping calls.

        Returns a list of repo dicts, each with at least:
            * ``"full_name"``  — e.g. ``"owner/repo"``
            * ``"description"`` — short description string
            * ``"stars"``      — integer star count
            * ``"language"``   — primary programming language
            * ``"url"``        — HTML URL of the repo
        """
        return []

    # ------------------------------------------------------------------
    # Core scan
    # ------------------------------------------------------------------

    def scan(self, ts_ns: int) -> list[dict]:
        """Scan all watched categories for newly discovered repositories.

        Runs ``_fetch_trending`` for each registered category, deduplicates
        against the known set, and emits a ledger event when new repos are
        found.

        Returns
        -------
        list[dict]
            Newly discovered repository dicts not seen in previous scans.
        """
        self._last_scan_ts_ns = ts_ns
        newly_found: list[dict] = []

        for category in self._categories:
            repos = self._fetch_trending(category)
            for repo in repos:
                full_name = repo.get("full_name", "")
                if not full_name:
                    continue
                if full_name not in self._discovered_repos:
                    enriched = dict(repo)
                    enriched["category"] = category
                    enriched["discovered_ts_ns"] = ts_ns
                    self._discovered_repos[full_name] = enriched
                    newly_found.append(enriched)

        if newly_found:
            append_event(
                "SYSTEM",
                "HEALTH_GITHUB_TRENDING",
                "system_engine.health_monitors.github_trending",
                {
                    "ts_ns": ts_ns,
                    "new_repo_count": len(newly_found),
                    "repos": str([r.get("full_name") for r in newly_found]),
                    "categories_scanned": str(list(self._categories)),
                },
            )

        return newly_found

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Return a serialisable snapshot of monitor state."""
        return {
            "categories": list(self._categories),
            "last_scan_ts_ns": self._last_scan_ts_ns,
            "discovered_repo_count": len(self._discovered_repos),
            "discovered_repos": {
                name: dict(info) for name, info in self._discovered_repos.items()
            },
        }


__all__ = ["GithubTrendingMonitor"]
