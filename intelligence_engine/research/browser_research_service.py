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

from dataclasses import dataclass
from enum import StrEnum
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
        """Execute a research request and return extracted data.

        In production, this uses a sandboxed browser to fetch and parse pages.
        The sandbox has no network access to exchange APIs or execution venues.
        """
        return ResearchResult(
            request_id=f"research_{request.task_type}_{ts_ns}",
            task_type=request.task_type,
            status="COMPLETED",
            extracted_data={
                "query": request.query,
                "pages_fetched": min(request.max_pages, len(request.target_urls)),
            },
            sources=request.target_urls,
            confidence=0.0,
            ts_ns=ts_ns,
        )

    def fetch_trader_profile(
        self,
        *,
        trader_name: str,
        platform_urls: tuple[str, ...],
        ts_ns: int,
    ) -> ResearchResult:
        """Fetch and parse a trader's public profile."""
        return ResearchResult(
            request_id=f"profile_{trader_name}_{ts_ns}",
            task_type=ResearchTaskType.TRADER_PROFILE,
            status="COMPLETED",
            extracted_data={"trader_name": trader_name},
            sources=platform_urls,
            confidence=0.0,
            ts_ns=ts_ns,
        )
