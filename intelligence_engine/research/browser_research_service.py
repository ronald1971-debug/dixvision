"""Browser research service (BUILD-DIRECTIVE §22).

Sandboxed research interface that can:
- Fetch and parse research reports (read-only)
- Extract trader profiles from public pages
- Collect market commentary and analysis

The service is sandboxed: no outbound execution, no credential access,
no side effects beyond reading. All results are observations that feed
into the intelligence pipeline.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from html.parser import HTMLParser
from typing import Any


class ResearchTaskType(StrEnum):
    """Type of research task."""

    TRADER_PROFILE = "TRADER_PROFILE"
    MARKET_ANALYSIS = "MARKET_ANALYSIS"
    STRATEGY_REPORT = "STRATEGY_REPORT"
    NEWS_DEEP_DIVE = "NEWS_DEEP_DIVE"
    ACADEMIC_PAPER = "ACADEMIC_PAPER"


@dataclass(frozen=True, slots=True)
class ResearchRequest:
    """A request for the browser research service."""

    task_type: ResearchTaskType
    query: str
    target_urls: tuple[str, ...] = ()
    max_pages: int = 5
    ts_ns: int = 0


@dataclass(frozen=True, slots=True)
class ResearchResult:
    """Result of a browser research task."""

    request_id: str
    task_type: ResearchTaskType
    status: str
    extracted_data: dict[str, Any]
    sources: tuple[str, ...]
    confidence: float
    ts_ns: int


_FETCH_TIMEOUT_S = 10
_USER_AGENT = "DIXVision-Research/1.0 (read-only; no execution)"
_MAX_BODY_BYTES = 256 * 1024  # 256 KiB cap per page
_BODY_EXCERPT_CHARS = 4096
_MIN_WORDS_FOR_CONTENT_SCORE = 2000

# Tags whose inner text carries no readable content
_SKIP_TAGS: frozenset[str] = frozenset(
    {"script", "style", "noscript", "head", "meta", "link", "svg", "canvas"}
)


class _TextExtractor(HTMLParser):
    """Strips HTML tags and collects visible text + page title."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0
        self._title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self._title_parts.append(text)
        if self._skip_depth == 0:
            self._parts.append(text)

    @property
    def body_text(self) -> str:
        return " ".join(self._parts)

    @property
    def title(self) -> str:
        return " ".join(self._title_parts).strip()


def _fetch_url(url: str) -> tuple[str, str]:
    """Fetch *url* and return (title, body_text). Raises on network/parse failure."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_S) as resp:  # noqa: S310
        raw: bytes = resp.read(_MAX_BODY_BYTES)
        charset: str = resp.headers.get_content_charset("utf-8") or "utf-8"
    html = raw.decode(charset, errors="replace")
    parser = _TextExtractor()
    parser.feed(html)
    return parser.title, parser.body_text


def _score_confidence(pages_ok: int, pages_attempted: int, total_words: int) -> float:
    """Heuristic [0, 1]: fetch success rate (0.7) + content volume (0.3)."""
    if pages_attempted == 0:
        return 0.0
    fetch_ratio = pages_ok / pages_attempted
    word_score = min(total_words / _MIN_WORDS_FOR_CONTENT_SCORE, 1.0) * 0.3
    return round(fetch_ratio * 0.7 + word_score, 4)


class BrowserResearchService:
    """Sandboxed browser research service.

    Read-only: extracts information from public web pages.
    No execution, no credentials, no side effects.
    """

    def fetch_research(
        self,
        request: ResearchRequest,
        *,
        ts_ns: int,
    ) -> ResearchResult:
        """Execute a research request and return extracted data."""
        urls = list(request.target_urls[: request.max_pages])
        pages: dict[str, dict[str, str]] = {}
        errors: dict[str, str] = {}

        for url in urls:
            try:
                title, body = _fetch_url(url)
                pages[url] = {"title": title, "body": body[:_BODY_EXCERPT_CHARS]}
            except Exception as exc:
                errors[url] = type(exc).__name__ + ": " + str(exc)

        total_words = sum(len(p["body"].split()) for p in pages.values())
        confidence = _score_confidence(len(pages), len(urls), total_words)

        extracted: dict[str, Any] = {
            "query": request.query,
            "pages_fetched": len(pages),
            "pages_attempted": len(urls),
            "pages": pages,
        }
        if errors:
            extracted["errors"] = errors

        if pages:
            status = "COMPLETED"
        elif urls:
            status = "FAILED"
        else:
            status = "NO_URLS"

        result = ResearchResult(
            request_id=f"research_{request.task_type}_{ts_ns}",
            task_type=request.task_type,
            status=status,
            extracted_data=extracted,
            sources=tuple(pages.keys()),
            confidence=confidence,
            ts_ns=ts_ns,
        )
        self._emit_research_discovery(result, topic=request.query)
        return result

    def fetch_trader_profile(
        self,
        *,
        trader_name: str,
        platform_urls: tuple[str, ...],
        ts_ns: int,
    ) -> ResearchResult:
        """Fetch and parse a trader's public profile pages."""
        pages: dict[str, dict[str, str]] = {}
        errors: dict[str, str] = {}

        for url in platform_urls:
            try:
                title, body = _fetch_url(url)
                pages[url] = {"title": title, "body": body[:_BODY_EXCERPT_CHARS]}
            except Exception as exc:
                errors[url] = type(exc).__name__ + ": " + str(exc)

        name_lower = trader_name.lower()
        name_mentions: dict[str, int] = {}
        for url, page in pages.items():
            count = page["body"].lower().count(name_lower)
            if count:
                name_mentions[url] = count

        total_words = sum(len(p["body"].split()) for p in pages.values())
        confidence = _score_confidence(len(pages), len(platform_urls), total_words)

        extracted: dict[str, Any] = {
            "trader_name": trader_name,
            "pages_fetched": len(pages),
            "pages": pages,
        }
        if name_mentions:
            extracted["name_mentions"] = name_mentions
        if errors:
            extracted["errors"] = errors

        if pages:
            status = "COMPLETED"
        elif platform_urls:
            status = "FAILED"
        else:
            status = "NO_URLS"

        result = ResearchResult(
            request_id=f"profile_{trader_name}_{ts_ns}",
            task_type=ResearchTaskType.TRADER_PROFILE,
            status=status,
            extracted_data=extracted,
            sources=tuple(pages.keys()),
            confidence=confidence,
            ts_ns=ts_ns,
        )
        self._emit_research_discovery(result, topic=f"trader_profile:{trader_name}")
        return result

    @staticmethod
    def _emit_research_discovery(result: ResearchResult, *, topic: str) -> None:
        """Best-effort ResearchDiscoveryEvent emission. Never raises."""
        try:
            from intelligence_engine.cognitive.observability_emitter import (
                emit_research_discovery,
            )

            primary_source = result.sources[0] if result.sources else ""
            emit_research_discovery(
                ts_ns=result.ts_ns,
                source_url=primary_source,
                topic=topic,
                summary=f"{result.task_type.value}: {topic}",
                confidence=result.confidence,
                connected_to=(),
                trust_score=0.5,
                discovery_id=result.request_id,
            )
        except Exception:  # pragma: no cover
            pass


__all__ = [
    "BrowserResearchService",
    "ResearchRequest",
    "ResearchResult",
    "ResearchTaskType",
]
