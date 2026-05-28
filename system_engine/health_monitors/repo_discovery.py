"""system_engine/health_monitors/repo_discovery.py
DIX VISION v42.2 — Repository Discovery Monitor

Periodically scans configured source-code repositories (GitHub,
GitLab, local paths) for dependency updates, new releases, and
security advisories relevant to the DIX VISION dependency graph.

Hazard sensor pattern: observe(ts_ns) returns HazardEvents; one-shot
per finding (no duplicate events until reset). Thread-safe.
"""

from __future__ import annotations

import hashlib
import threading
import time as _time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from typing import Any

from system_engine.hazard_sensors.base import HazardEvent, HazardSeverity


_WINDOW = 200
_CHECK_INTERVAL_S = 3600   # check once per hour


@dataclass(frozen=True, slots=True)
class RepoRelease:
    """A detected new release in a tracked repository."""
    repo: str
    tag: str
    published_at: str
    is_security: bool


class RepoDiscoveryMonitor:
    """
    Monitors tracked repositories for new releases and security advisories.

    Thread-safe. Callers call observe(ts_ns) to get pending HazardEvents.
    """

    def __init__(
        self,
        tracked_repos: list[str] | None = None,
        github_token: str | None = None,
        check_interval_s: float = _CHECK_INTERVAL_S,
    ) -> None:
        self._tracked_repos = tracked_repos or []
        self._github_token = github_token
        self._check_interval_s = check_interval_s
        self._lock = threading.Lock()
        self._window: deque[HazardEvent] = deque(maxlen=_WINDOW)
        self._emitted_ids: set[str] = set()
        self._last_check_s: float = 0.0
        self._known_tags: dict[str, str] = {}   # repo → latest known tag

    def add_repo(self, repo: str) -> None:
        with self._lock:
            if repo not in self._tracked_repos:
                self._tracked_repos.append(repo)

    def observe(self, ts_ns: int) -> tuple[HazardEvent, ...]:
        now_s = ts_ns / 1e9
        with self._lock:
            if now_s - self._last_check_s < self._check_interval_s:
                return ()
            self._last_check_s = now_s

        events: list[HazardEvent] = []
        for repo in list(self._tracked_repos):
            release = self._fetch_latest_release(repo)
            if release is None:
                continue
            event_id = hashlib.md5(f"{repo}:{release.tag}".encode()).hexdigest()
            with self._lock:
                if event_id in self._emitted_ids:
                    continue
                self._emitted_ids.add(event_id)

            severity = HazardSeverity.HIGH if release.is_security else HazardSeverity.LOW
            evt = HazardEvent(
                hazard_id=f"REPO_DISC_{event_id[:8].upper()}",
                source="repo_discovery",
                severity=severity,
                description=f"New {'security ' if release.is_security else ''}release {release.tag} in {repo}",
                ts_ns=ts_ns,
                meta={"repo": repo, "tag": release.tag, "published_at": release.published_at},
            )
            events.append(evt)
            with self._lock:
                self._window.append(evt)

        return tuple(events)

    def _fetch_latest_release(self, repo: str) -> RepoRelease | None:
        """Fetch the latest GitHub release for owner/repo."""
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        if self._github_token:
            headers["Authorization"] = f"Bearer {self._github_token}"
        try:
            import json
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = json.loads(resp.read())
            tag = body.get("tag_name", "")
            if not tag or tag == self._known_tags.get(repo):
                return None
            self._known_tags[repo] = tag
            published = body.get("published_at", "")
            body_text = body.get("body", "").lower()
            is_security = any(k in body_text for k in ("cve-", "security", "vulnerability"))
            return RepoRelease(
                repo=repo,
                tag=tag,
                published_at=published,
                is_security=is_security,
            )
        except Exception:
            return None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "tracked_repos": list(self._tracked_repos),
                "events_emitted": len(self._emitted_ids),
                "window_size": len(self._window),
            }


__all__ = ["RepoDiscoveryMonitor", "RepoRelease"]
