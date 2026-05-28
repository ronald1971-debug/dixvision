"""TI-ING-02 — trader profile extractor.

Extracts structured trader profile fields from raw crawled HTML.
Pure computation (no I/O). INV-15. B1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["TraderProfile", "ProfileExtractor"]


@dataclass(frozen=True, slots=True)
class TraderProfile:
    source_id: str
    ts_ns: int
    handle: str
    bio: str
    follower_count: int
    following_count: int
    post_count: int
    verified: bool
    raw_tags: tuple[str, ...]


_FOLLOWER_RE = re.compile(r"(\d[\d,\.]*)\s*(?:followers?|Followers?)")
_FOLLOWING_RE = re.compile(r"(\d[\d,\.]*)\s*(?:following|Following)")
_POST_RE = re.compile(r"(\d[\d,\.]*)\s*(?:posts?|Tweets?|posts?)")


def _parse_int(raw: str) -> int:
    cleaned = raw.replace(",", "").replace(".", "")
    try:
        return int(cleaned)
    except ValueError:
        return 0


class ProfileExtractor:
    """Extract trader profile data from raw HTML using regex heuristics.

    Designed for social-media and forum trader pages. Returns a
    TraderProfile with best-effort field extraction.
    """

    def extract(self, source_id: str, ts_ns: int, raw_html: str) -> TraderProfile:
        handle = self._extract_handle(raw_html)
        bio = self._extract_bio(raw_html)
        followers = self._extract_count(raw_html, _FOLLOWER_RE)
        following = self._extract_count(raw_html, _FOLLOWING_RE)
        posts = self._extract_count(raw_html, _POST_RE)
        verified = "verified" in raw_html.lower() or "✓" in raw_html
        tags = self._extract_tags(raw_html)
        return TraderProfile(
            source_id=source_id,
            ts_ns=ts_ns,
            handle=handle,
            bio=bio,
            follower_count=followers,
            following_count=following,
            post_count=posts,
            verified=verified,
            raw_tags=tuple(tags),
        )

    def _extract_handle(self, html: str) -> str:
        m = re.search(r'@([\w_]{2,32})', html)
        return m.group(1) if m else ""

    def _extract_bio(self, html: str) -> str:
        m = re.search(r'<(?:p|span)[^>]*class="[^"]*bio[^"]*"[^>]*>([^<]{5,300})<', html, re.I)
        return m.group(1).strip() if m else ""

    def _extract_count(self, html: str, pattern: re.Pattern[str]) -> int:
        m = pattern.search(html)
        return _parse_int(m.group(1)) if m else 0

    def _extract_tags(self, html: str) -> list[str]:
        return re.findall(r'#([\w_]{2,30})', html)[:20]
