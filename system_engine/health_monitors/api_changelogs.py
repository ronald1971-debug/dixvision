"""API changelog health monitor.

Monitors external API changelog feeds to detect breaking changes before
they hit production. Actual HTTP fetching is deliberately deferred — the
base implementation registers intent and tracks watched APIs; subclasses
or injected fetch hooks may override ``_fetch_changelog`` to activate
real network calls.

Emits ``SYSTEM/HEALTH_API_CHANGELOG_CHANGE`` events to the ledger when
version changes or deprecation notices are detected.
"""

from __future__ import annotations

import threading

from state.ledger.event_store import append_event


class APIChangelogMonitor:
    """Monitors external API changelog feeds for breaking changes.

    The base class keeps the network boundary explicit: no HTTP calls are
    made in ``__init__`` or ``check``. Subclasses override
    ``_fetch_changelog`` to activate real fetching.
    """

    name: str = "api_changelog_monitor"
    spec_id: str = "SYS-HEALTH-ACL-01"

    __slots__ = ("_watched_apis", "_last_check_ts_ns", "_detected_changes")

    def __init__(self) -> None:
        # key: api_name → {"url": str, "current_version": str}
        self._watched_apis: dict[str, dict[str, str]] = {}
        self._last_check_ts_ns: int = 0
        # key: api_name → list of change dicts
        self._detected_changes: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_api(
        self,
        api_name: str,
        changelog_url: str,
        current_version: str,
    ) -> None:
        """Register an API to watch.

        Parameters
        ----------
        api_name:
            Stable identifier for the API (e.g. ``"alpaca_trading"``).
        changelog_url:
            URL of the changelog feed (RSS, JSON, or HTML page).
        current_version:
            The currently deployed/pinned version string.
        """
        if not api_name:
            raise ValueError("api_name must be non-empty")
        self._watched_apis[api_name] = {
            "url": changelog_url,
            "current_version": current_version,
        }
        if api_name not in self._detected_changes:
            self._detected_changes[api_name] = []

    # ------------------------------------------------------------------
    # Fetch hook (override in subclasses / tests)
    # ------------------------------------------------------------------

    def _fetch_changelog(self, api_name: str, changelog_url: str) -> list[dict]:
        """Fetch changelog entries for one API.

        Base implementation is a no-op returning an empty list. Override
        this method to activate real HTTP fetching.

        Returns a list of change dicts, each with at least:
            * ``"version"``    — version string
            * ``"kind"``       — e.g. ``"version_bump"``, ``"deprecation"``
            * ``"summary"``    — human-readable summary
        """
        return []

    # ------------------------------------------------------------------
    # Core check
    # ------------------------------------------------------------------

    def check(self, ts_ns: int) -> list[dict]:
        """Check all registered APIs for changelog changes.

        Runs ``_fetch_changelog`` for each registered API, compares against
        the known ``current_version``, and collects new changes. Emits a
        ledger event for each API that has new changes.

        Returns
        -------
        list[dict]
            All new change dicts collected across all watched APIs.
        """
        self._last_check_ts_ns = ts_ns
        all_new: list[dict] = []

        for api_name, info in self._watched_apis.items():
            entries = self._fetch_changelog(api_name, info["url"])
            current = info["current_version"]
            new_entries: list[dict] = []
            for entry in entries:
                version = entry.get("version", "")
                kind = entry.get("kind", "unknown")
                # Accept anything newer than current or a deprecation notice.
                if version and version != current:
                    new_entries.append(entry)
                elif kind == "deprecation":
                    new_entries.append(entry)

            if new_entries:
                self._detected_changes.setdefault(api_name, []).extend(new_entries)
                all_new.extend(new_entries)
                append_event(
                    "SYSTEM",
                    "HEALTH_API_CHANGELOG_CHANGE",
                    "system_engine.health_monitors.api_changelogs",
                    {
                        "api_name": api_name,
                        "ts_ns": ts_ns,
                        "current_version": current,
                        "new_change_count": len(new_entries),
                        "changes": str(new_entries),
                    },
                )

        return all_new

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Return a serialisable snapshot of monitor state."""
        return {
            "watched_apis": {
                name: dict(info) for name, info in self._watched_apis.items()
            },
            "last_check_ts_ns": self._last_check_ts_ns,
            "detected_changes": {
                name: list(changes)
                for name, changes in self._detected_changes.items()
            },
        }


__all__ = ["APIChangelogMonitor"]
