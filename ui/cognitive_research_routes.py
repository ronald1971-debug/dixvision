"""Cognitive research routes — P4 autonomous knowledge acquisition surface.

REST endpoints for INDIRA's autonomous research runtime: topic ingestion,
queue status, and recent result inspection.

Routes:
  POST /api/cognitive/research/enqueue   — submit a research topic
  GET  /api/cognitive/research/status    — queue depth + runtime stats
  GET  /api/cognitive/research/results   — recent completed research results

All writes go to the AutonomousResearchRuntime singleton queue.
No engine cross-imports — authority boundary preserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from system.time_source import utc_now


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ResearchEnqueueRequest(BaseModel):
    """Body for POST /api/cognitive/research/enqueue."""

    topic: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Research subject (free-text query or named topic).",
    )
    task_type: str = Field(
        default="MARKET_ANALYSIS",
        description=(
            "One of: TRADER_PROFILE, MARKET_ANALYSIS, STRATEGY_REPORT, "
            "NEWS_DEEP_DIVE, ACADEMIC_PAPER."
        ),
    )
    target_urls: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Optional list of specific URLs to fetch (up to 10).",
    )
    max_pages: int = Field(default=3, ge=1, le=10)
    priority: int = Field(
        default=5,
        ge=1,
        le=10,
        description="1 = highest priority, 10 = lowest. Lower values are processed first.",
    )


class ResearchEnqueueResponse(BaseModel):
    ts_iso: str
    topic: str
    task_type: str
    priority: int
    queue_depth: int
    message: str


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def build_cognitive_research_router() -> APIRouter:
    """Construct the cognitive research router."""

    router = APIRouter(prefix="/api/cognitive/research", tags=["cognitive-research"])

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    @router.post("/enqueue")
    def enqueue_research(body: ResearchEnqueueRequest) -> ResearchEnqueueResponse:
        """Submit a research topic to INDIRA's autonomous research queue.

        The topic is processed by the background research loop in priority
        order. Results appear in ``GET /api/cognitive/research/results``
        once the run completes and as ResearchDiscoveryEvents on the
        cognitive SSE stream.
        """
        from intelligence_engine.research.autonomous_research_runtime import (
            ResearchTopic,
            get_research_runtime,
        )
        from intelligence_engine.research.browser_research_service import ResearchTaskType
        import time

        try:
            task_type = ResearchTaskType(body.task_type)
        except ValueError:
            task_type = ResearchTaskType.MARKET_ANALYSIS

        topic = ResearchTopic(
            topic=body.topic,
            task_type=task_type,
            target_urls=tuple(body.target_urls),
            max_pages=body.max_pages,
            priority=body.priority,
            ts_ns=time.time_ns(),
        )
        runtime = get_research_runtime()
        depth = runtime.enqueue(topic)

        return ResearchEnqueueResponse(
            ts_iso=utc_now().isoformat(),
            topic=body.topic,
            task_type=task_type.value,
            priority=body.priority,
            queue_depth=depth,
            message="Topic queued for autonomous research.",
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @router.get("/status")
    def research_status() -> dict[str, Any]:
        """Current status of INDIRA's autonomous research runtime.

        Returns queue depth, processing stats, recent activity count,
        and a preview of the next N queued topics.
        """
        from intelligence_engine.research.autonomous_research_runtime import (
            get_research_runtime,
        )
        runtime = get_research_runtime()
        snap = runtime.snapshot()
        snap["ts_iso"] = utc_now().isoformat()
        return snap

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    @router.get("/results")
    def research_results(limit: int = 20) -> dict[str, Any]:
        """Recent completed autonomous research results.

        Returns newest-first. Each record contains topic, status,
        pages_fetched, confidence, trust_score, sources, ts_ns.
        """
        from intelligence_engine.research.autonomous_research_runtime import (
            get_research_runtime,
        )
        n = max(1, min(limit, 200))
        runtime = get_research_runtime()
        results = runtime.recent_results(n)
        return {
            "ts_iso": utc_now().isoformat(),
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }

    return router


__all__ = ["build_cognitive_research_router"]
