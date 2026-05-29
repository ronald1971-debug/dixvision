"""Autonomous Research Runtime — INDIRA's always-on knowledge acquisition (P4).

INDIRA continuously researches market intelligence: trader profiles, market
analysis, academic papers, strategy reports. This module owns the research
queue, background fetcher loop, source trust scoring, and memory graph storage.

Design:
* ResearchQueue: priority-ordered bounded deque of ResearchTopics.
* Background daemon thread: dequeues, runs the configured backend, stores
  findings in SemanticMemoryStore, emits ResearchDiscoveryEvent.
* SourceTrustScorer: deterministic domain → [0, 1] trust tier lookup.
* Embedding: deterministic hash-projection for SemanticMemoryStore (INV-15).

Research backends (in priority order at fetch time):
  1. Firecrawl API — if FIRECRAWL_API_KEY env var is set (AI-powered extraction)
  2. Playwright headless — if `playwright` package is importable (JS-heavy pages)
  3. BrowserResearchService — always available (urllib HTML fetch + text extraction)

Authority (B1): imports only from intelligence_engine.* and core.*.
INV-15: timestamps are caller-supplied or ``time.time_ns()`` at emission time only.
"""

from __future__ import annotations

import hashlib
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from intelligence_engine.research.browser_research_service import (
    BrowserResearchService,
    ResearchRequest,
    ResearchResult,
    ResearchTaskType,
)


# ---------------------------------------------------------------------------
# Source trust scoring
# ---------------------------------------------------------------------------

_DOMAIN_TRUST: dict[str, float] = {
    # High-trust institutional / financial
    "bloomberg.com": 0.90,
    "reuters.com": 0.90,
    "ft.com": 0.88,
    "wsj.com": 0.88,
    "arxiv.org": 0.92,
    "ssrn.com": 0.90,
    "papers.ssrn.com": 0.90,
    # Crypto-native high-trust
    "coindesk.com": 0.85,
    "cointelegraph.com": 0.80,
    "theblock.co": 0.82,
    "decrypt.co": 0.78,
    "messari.io": 0.83,
    "dune.com": 0.80,
    "glassnode.com": 0.82,
    # Analysis / commentary — medium trust
    "tradingview.com": 0.65,
    "seekingalpha.com": 0.65,
    "investing.com": 0.63,
    "finviz.com": 0.65,
    "medium.com": 0.55,
    "substack.com": 0.60,
    # Social / unverified — low trust
    "twitter.com": 0.38,
    "x.com": 0.38,
    "reddit.com": 0.33,
    "youtube.com": 0.32,
    "t.me": 0.25,
}

_DEFAULT_TRUST = 0.45


def score_source_trust(url: str) -> float:
    """Return [0, 1] trust score for url's domain (deterministic lookup)."""
    if not url:
        return _DEFAULT_TRUST
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain in _DOMAIN_TRUST:
            return _DOMAIN_TRUST[domain]
        parts = domain.split(".")
        if len(parts) >= 2:
            parent = ".".join(parts[-2:])
            if parent in _DOMAIN_TRUST:
                return _DOMAIN_TRUST[parent]
    except Exception:
        pass
    return _DEFAULT_TRUST


# ---------------------------------------------------------------------------
# Deterministic text embedding for SemanticMemoryStore (INV-15)
# ---------------------------------------------------------------------------

_EMBED_DIM = 64


def _text_embedding(text: str, dim: int = _EMBED_DIM) -> tuple[float, ...]:
    """Produce a deterministic dim-dimensional unit embedding from text.

    Uses SHA-256 hash bytes as the seed, then adds character-frequency
    contributions. All arithmetic is deterministic — no PRNG, no clock.
    """
    vec = [0.0] * dim
    # Hash-based projection: spread 32 digest bytes across dim slots
    h = hashlib.sha256(text.encode("utf-8", errors="replace")).digest()
    for i in range(dim):
        vec[i] += float(h[i % 32])
    # Character-frequency contribution (first 512 chars)
    for i, ch in enumerate(text[:512]):
        vec[(ord(ch) + i * 7) % dim] += 0.5
    # L2-normalize to unit sphere
    norm = math.sqrt(sum(x * x for x in vec))
    if norm < 1e-10:
        return tuple(1.0 / math.sqrt(dim) for _ in range(dim))
    return tuple(x / norm for x in vec)


# ---------------------------------------------------------------------------
# ResearchTopic
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResearchTopic:
    """A queued research topic for autonomous acquisition."""

    topic: str
    task_type: ResearchTaskType = ResearchTaskType.MARKET_ANALYSIS
    target_urls: tuple[str, ...] = ()
    max_pages: int = 3
    priority: int = 5      # 1 (highest) to 10 (lowest); lower = dequeued sooner
    ts_ns: int = 0         # enqueue timestamp for FIFO within same priority


# ---------------------------------------------------------------------------
# Research result snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResearchSnapshot:
    """Lightweight summary of a completed research run."""

    topic: str
    task_type: str
    status: str
    pages_fetched: int
    confidence: float
    trust_score: float
    sources: tuple[str, ...]
    ts_ns: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "task_type": self.task_type,
            "status": self.status,
            "pages_fetched": self.pages_fetched,
            "confidence": self.confidence,
            "trust_score": self.trust_score,
            "sources": list(self.sources),
            "ts_ns": self.ts_ns,
        }


# ---------------------------------------------------------------------------
# Firecrawl backend (optional — requires FIRECRAWL_API_KEY)
# ---------------------------------------------------------------------------


def _firecrawl_fetch(url: str) -> tuple[str, str] | None:
    """Fetch url via Firecrawl API. Returns (title, markdown) or None on failure."""
    api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import urllib.request as _req
        import json as _json
        body = _json.dumps({"url": url, "formats": ["markdown"]}).encode()
        request = _req.Request(
            "https://api.firecrawl.dev/v1/scrape",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with _req.urlopen(request, timeout=15) as resp:
            data = _json.loads(resp.read())
        md = data.get("data", {}).get("markdown", "") or ""
        title = data.get("data", {}).get("metadata", {}).get("title", url)
        return title, md[:8192]
    except Exception:
        return None


def _playwright_fetch(url: str) -> tuple[str, str] | None:
    """Fetch url via Playwright headless chromium. Returns (title, text) or None."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import]
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            title = page.title()
            text = page.inner_text("body")[:8192]
            browser.close()
        return title, text
    except Exception:
        return None


# ---------------------------------------------------------------------------
# AutonomousResearchRuntime
# ---------------------------------------------------------------------------


class AutonomousResearchRuntime:
    """INDIRA's always-on autonomous research loop.

    Maintains a priority queue of ResearchTopics and processes them on a
    background daemon thread. Results are stored in SemanticMemoryStore and
    emitted as ResearchDiscoveryEvents to the cognitive observability ledger.

    Args:
        max_queue_depth: Maximum number of pending topics; oldest low-priority
            topics are evicted when the queue is full.
        max_history: Rolling buffer depth for recent result snapshots.
        fetch_interval_s: Seconds to wait between research runs.
    """

    def __init__(
        self,
        *,
        max_queue_depth: int = 200,
        max_history: int = 100,
        fetch_interval_s: float = 60.0,
    ) -> None:
        self._lock = threading.Lock()
        self._queue: list[ResearchTopic] = []         # sorted by (priority, ts_ns)
        self._max_queue = max_queue_depth
        self._history: deque[ResearchSnapshot] = deque(maxlen=max_history)
        self._fetch_interval = fetch_interval_s
        self._browser_service = BrowserResearchService()
        self._total_runs: int = 0
        self._total_ok: int = 0
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._semantic_store: Any = None   # SemanticMemoryStore, lazy-init

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def enqueue(self, topic: ResearchTopic) -> int:
        """Add a topic to the research queue. Returns current queue depth."""
        with self._lock:
            # Deduplicate: skip if exact same topic string already queued
            if any(t.topic == topic.topic for t in self._queue):
                return len(self._queue)
            self._queue.append(topic)
            self._queue.sort(key=lambda t: (t.priority, t.ts_ns))
            # Evict lowest-priority topics if over capacity
            while len(self._queue) > self._max_queue:
                self._queue.pop()  # highest index = lowest priority (sorted)
            depth = len(self._queue)
        # Persist new task so it survives restart (best-effort)
        try:
            from state.cognition_persistence import get_cognition_persistence_store
            get_cognition_persistence_store().enqueue_research(
                topic=topic.topic,
                task_type=topic.task_type.value,
                priority=topic.priority,
                ts_ns=topic.ts_ns,
            )
        except Exception:
            pass
        return depth

    def queue_depth(self) -> int:
        with self._lock:
            return len(self._queue)

    def _pop_next(self) -> ResearchTopic | None:
        with self._lock:
            return self._queue.pop(0) if self._queue else None

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background research daemon. Idempotent."""
        with self._lock:
            if self._running:
                return
            self._running = True
        # Reload any tasks that were pending when the process last stopped.
        self._restore_queue_from_persistence()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="indira-research"
        )
        self._thread.start()

    def _restore_queue_from_persistence(self) -> None:
        """Re-enqueue PENDING tasks from the SQLite persistence store."""
        try:
            from state.cognition_persistence import get_cognition_persistence_store
            rows = get_cognition_persistence_store().load_pending_queue()
            for row in rows:
                try:
                    task_type_str = row.get("task_type", "MARKET_ANALYSIS")
                    # Map string → ResearchTaskType enum
                    try:
                        task_type = ResearchTaskType(task_type_str)
                    except ValueError:
                        task_type = ResearchTaskType.MARKET_ANALYSIS
                    rt = ResearchTopic(
                        topic=row["topic"],
                        task_type=task_type,
                        target_urls=(),
                        max_pages=3,
                        priority=int(row.get("priority", 5)),
                        ts_ns=int(row.get("ts_ns", 0)),
                    )
                    with self._lock:
                        if not any(t.topic == rt.topic for t in self._queue):
                            self._queue.append(rt)
                except Exception:
                    pass
            if self._queue:
                with self._lock:
                    self._queue.sort(key=lambda t: (t.priority, t.ts_ns))
        except Exception:
            pass

    def stop(self) -> None:
        """Signal the background loop to stop (best-effort)."""
        with self._lock:
            self._running = False

    def _loop(self) -> None:
        while True:
            with self._lock:
                if not self._running:
                    return
            topic = self._pop_next()
            if topic is not None:
                try:
                    self._run_research(topic)
                except Exception:
                    pass
            time.sleep(self._fetch_interval)

    # ------------------------------------------------------------------
    # Research execution
    # ------------------------------------------------------------------

    def _run_research(self, topic: ResearchTopic) -> None:
        """Execute one research run: fetch → score → store → emit."""
        from system.time_source import wall_ns as _wall_ns
        ts_ns = _wall_ns()

        # ---- 1. Fetch ----
        pages: dict[str, dict[str, str]] = {}
        urls = list(topic.target_urls[: topic.max_pages])

        for url in urls:
            # Backend priority: Firecrawl → Playwright → urllib
            result = _firecrawl_fetch(url)
            if result is None:
                result = _playwright_fetch(url)
            if result is None:
                try:
                    from intelligence_engine.research.browser_research_service import (
                        _fetch_url,
                    )
                    result = _fetch_url(url)
                except Exception:
                    continue
            if result:
                title, body = result
                pages[url] = {"title": title, "body": body[:4096]}

        if not pages and not urls:
            # Query-only topic: emit a reflection thought without fetching
            self._emit_discovery(
                topic=topic.topic,
                source_url="",
                summary=f"Research queue: {topic.topic}",
                confidence=0.3,
                trust_score=_DEFAULT_TRUST,
                ts_ns=ts_ns,
            )
            return

        # ---- 2. Score trust ----
        primary_url = next(iter(pages), urls[0] if urls else "")
        trust_score = score_source_trust(primary_url)

        total_words = sum(len(p["body"].split()) for p in pages.values())
        from intelligence_engine.research.browser_research_service import _score_confidence
        raw_confidence = _score_confidence(len(pages), len(urls) or 1, total_words)
        # Blend with source trust
        confidence = round(raw_confidence * 0.7 + trust_score * 0.3, 4)

        # ---- 3. Build summary text for embedding ----
        summary_parts = [topic.topic]
        for url, page in pages.items():
            summary_parts.append(page.get("title", ""))
            summary_parts.append(page.get("body", "")[:512])
        summary_text = " ".join(p for p in summary_parts if p)

        # ---- 4. Store finding in SemanticMemoryStore (best-effort) ----
        self._store_memory(
            topic=topic.topic,
            text=summary_text,
            source_url=primary_url,
            trust_score=trust_score,
            confidence=confidence,
            ts_ns=ts_ns,
        )

        # ---- 5. Emit ResearchDiscoveryEvent ----
        summary = f"{topic.task_type.value}: {topic.topic} ({len(pages)} pages)"
        self._emit_discovery(
            topic=topic.topic,
            source_url=primary_url,
            summary=summary,
            confidence=confidence,
            trust_score=trust_score,
            ts_ns=ts_ns,
        )

        # ---- 6. Record snapshot ----
        status = "COMPLETED" if pages else "FAILED"
        snap = ResearchSnapshot(
            topic=topic.topic,
            task_type=topic.task_type.value,
            status=status,
            pages_fetched=len(pages),
            confidence=confidence,
            trust_score=trust_score,
            sources=tuple(pages.keys()),
            ts_ns=ts_ns,
        )
        with self._lock:
            self._history.appendleft(snap)
            self._total_runs += 1
            if pages:
                self._total_ok += 1

        # ---- 7. Persist result and mark queue item done ----
        try:
            from state.cognition_persistence import get_cognition_persistence_store
            ps = get_cognition_persistence_store()
            ps.save_research_result(
                topic=topic.topic,
                task_type=topic.task_type.value,
                status=status,
                pages_fetched=len(pages),
                confidence=confidence,
                trust_score=trust_score,
                sources=list(pages.keys()),
                ts_ns=ts_ns,
            )
            ps.mark_queue_done(topic=topic.topic)
        except Exception:
            pass
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.RESEARCH_COMPLETE, {
                "topic": topic.topic,
                "status": status,
                "pages_fetched": len(pages),
                "confidence": confidence,
                "trust_score": trust_score,
                "ts_ns": ts_ns,
            })
        except Exception:
            pass

    def _store_memory(
        self,
        *,
        topic: str,
        text: str,
        source_url: str,
        trust_score: float,
        confidence: float,
        ts_ns: int,
    ) -> None:
        """Best-effort storage of research finding in SemanticMemoryStore."""
        try:
            from state.memory_tensor.semantic import SemanticMemoryStore
            from state.memory_tensor.contracts import Episode
            from types import MappingProxyType

            # Lazy-init the store; dim must match _EMBED_DIM
            if self._semantic_store is None:
                self._semantic_store = SemanticMemoryStore(dim=_EMBED_DIM, max_size=1000)
            embedding = _text_embedding(text)
            episode = Episode(
                ts_ns=ts_ns,
                episode_id=f"research_{ts_ns}_{hash(topic) & 0xFFFFFFFF:08x}",
                embedding=embedding,
                payload=MappingProxyType({
                    "subject": topic[:64],
                    "content_summary": text[:256],
                    "source": source_url[:128],
                    "trust_score": f"{trust_score:.4f}",
                    "confidence": f"{confidence:.4f}",
                    "memory_kind": "research",
                }),
            )
            self._semantic_store.add(episode)
        except Exception:
            pass

    @staticmethod
    def _emit_discovery(
        *,
        topic: str,
        source_url: str,
        summary: str,
        confidence: float,
        trust_score: float,
        ts_ns: int,
    ) -> None:
        """Best-effort ResearchDiscoveryEvent emission. Never raises."""
        try:
            from intelligence_engine.cognitive.observability_emitter import (
                emit_research_discovery,
            )
            discovery_id = f"auto_research_{ts_ns}_{hash(topic) & 0xFFFF:04x}"
            emit_research_discovery(
                ts_ns=ts_ns,
                source_url=source_url,
                topic=topic,
                summary=summary,
                confidence=confidence,
                connected_to=(),
                trust_score=trust_score,
                discovery_id=discovery_id,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Operator surface
    # ------------------------------------------------------------------

    def recent_results(self, limit: int = 20) -> list[ResearchSnapshot]:
        """Return the most recent completed research snapshots, newest-first."""
        with self._lock:
            return list(self._history)[:limit]

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serialisable status snapshot."""
        with self._lock:
            queue_preview = [
                {"topic": t.topic, "priority": t.priority, "task_type": t.task_type.value}
                for t in self._queue[:10]
            ]
            return {
                "running": self._running,
                "queue_depth": len(self._queue),
                "queue_preview": queue_preview,
                "total_runs": self._total_runs,
                "total_ok": self._total_ok,
                "fetch_interval_s": self._fetch_interval,
                "recent_count": len(self._history),
            }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_runtime: AutonomousResearchRuntime | None = None
_runtime_lock = threading.Lock()


def get_research_runtime(
    *,
    fetch_interval_s: float = 60.0,
) -> AutonomousResearchRuntime:
    """Return the module-level singleton AutonomousResearchRuntime."""
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = AutonomousResearchRuntime(fetch_interval_s=fetch_interval_s)
            _runtime.start()
    return _runtime


__all__ = [
    "AutonomousResearchRuntime",
    "ResearchSnapshot",
    "ResearchTopic",
    "get_research_runtime",
    "score_source_trust",
]
