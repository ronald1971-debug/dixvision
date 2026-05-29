"""INDIRA Backtesting Platform Registry — autonomous discovery and connection (CONSOLIDATION PHASE).

INDIRA autonomously connects to and evaluates backtesting platforms:

Known platforms (seeded at boot):
    backtestic      — https://backtestic.io    (300+ instruments, candle replay)
    tradingview     — https://tradingview.com  (Bar Replay, PineScript alerts)
    mt4             — https://metatrader4.com  (Strategy Tester, EAs)
    traders_casa    — https://traderscasa.com  (free forex + crypto)
    quantconnect    — https://quantconnect.com (algorithmic, Python native)
    freqtrade       — https://freqtrade.io     (crypto bot + backtest CLI)
    jesse           — https://jesse.trade      (crypto backtesting Python)
    vectorbt        — https://vectorbt.pro     (vectorized NumPy backtesting)

Autonomous discovery:
    Every research_cycle() call enqueues a set of discovery topics into
    INDIRA's AutonomousResearchRuntime.  Every probe_cycle() call runs
    api_sniffer.propose_candidate() on pending platform URLs and updates
    connection status.  Both findings are emitted as RESEARCH_DISCOVERY
    cognitive events so the INDIRA dashboard widget shows live progress.

Authority (B1): imports from intelligence_engine.* and core.* only.
INV-15: all ts_ns values are caller-supplied.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BacktestPlatform:
    name: str
    base_url: str
    api_kind: str           # "rest" | "websocket" | "cli" | "python_lib"
    capabilities: tuple[str, ...]   # "backtest" | "live_data" | "replay" | "alerts"
    auth_type: str          # "apikey" | "bearer" | "none"
    trust_score: float      # operator-assigned [0, 1]
    notes: str = ""


@dataclass
class PlatformConnection:
    platform: BacktestPlatform
    status: str = "PENDING"         # PENDING | PROBING | CONNECTED | UNREACHABLE
    last_probe_ns: int = 0
    api_surfaces: list[str] = field(default_factory=list)
    relevance_score: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# Seed catalogue — platforms INDIRA knows about from birth
# ---------------------------------------------------------------------------

_SEED: tuple[BacktestPlatform, ...] = (
    BacktestPlatform(
        name="backtestic",
        base_url="https://backtestic.io",
        api_kind="rest",
        capabilities=("backtest", "replay", "live_data"),
        auth_type="none",
        trust_score=0.72,
        notes="Free tier: 2 sessions, 300+ instruments, candle-by-candle replay",
    ),
    BacktestPlatform(
        name="tradingview",
        base_url="https://tradingview.com",
        api_kind="rest",
        capabilities=("replay", "alerts", "live_data"),
        auth_type="bearer",
        trust_score=0.65,
        notes="Bar Replay; webhook alerts; PineScript strategy export",
    ),
    BacktestPlatform(
        name="mt4",
        base_url="https://metatrader4.com",
        api_kind="rest",
        capabilities=("backtest", "live_data"),
        auth_type="none",
        trust_score=0.68,
        notes="Strategy Tester + EA backtest; ZeroMQ bridge for programmatic access",
    ),
    BacktestPlatform(
        name="traders_casa",
        base_url="https://traderscasa.com",
        api_kind="rest",
        capabilities=("backtest", "replay"),
        auth_type="none",
        trust_score=0.60,
        notes="Free forex + crypto; mobile + desktop; partial-close support",
    ),
    BacktestPlatform(
        name="quantconnect",
        base_url="https://quantconnect.com",
        api_kind="rest",
        capabilities=("backtest", "live_data", "alerts"),
        auth_type="apikey",
        trust_score=0.82,
        notes="Python-native LEAN engine; REST + WebSocket API; tick-level data",
    ),
    BacktestPlatform(
        name="freqtrade",
        base_url="https://freqtrade.io",
        api_kind="cli",
        capabilities=("backtest",),
        auth_type="none",
        trust_score=0.75,
        notes="Crypto bot + CLI backtest; REST API for remote control",
    ),
    BacktestPlatform(
        name="jesse",
        base_url="https://jesse.trade",
        api_kind="python_lib",
        capabilities=("backtest",),
        auth_type="none",
        trust_score=0.71,
        notes="Python crypto backtesting; deterministic; extensible strategies",
    ),
    BacktestPlatform(
        name="vectorbt",
        base_url="https://vectorbt.pro",
        api_kind="python_lib",
        capabilities=("backtest",),
        auth_type="none",
        trust_score=0.78,
        notes="Vectorized NumPy/Pandas backtesting; extremely fast batch runs",
    ),
)

# Research topics INDIRA enqueues to discover MORE platforms autonomously
_RESEARCH_TOPICS = (
    "free backtesting platform API documentation 2024",
    "algorithmic trading backtesting tools open source",
    "crypto backtesting platforms comparison REST API",
    "paper trading simulator API free",
    "forex backtesting tool programmatic access",
    "strategy backtesting platform webhook integration",
)


# ---------------------------------------------------------------------------
# PlatformRegistry
# ---------------------------------------------------------------------------

class PlatformRegistry:
    """Registry of backtesting platforms INDIRA can connect to and test on.

    Maintains connection state for all known platforms, probes their API
    surfaces, and hands new platform discoveries to the AutonomousResearchRuntime.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connections: dict[str, PlatformConnection] = {
            p.name: PlatformConnection(platform=p) for p in _SEED
        }
        self._probe_seq: int = 0
        self._research_seq: int = 0
        self._research_started: bool = False

    # ------------------------------------------------------------------
    # Probe cycle — called from IndiraRuntime every N ticks
    # ------------------------------------------------------------------

    def probe_cycle(self, *, ts_ns: int) -> None:
        """Probe one PENDING platform per call (round-robin, best-effort)."""
        self._probe_seq += 1
        with self._lock:
            pending = [
                c for c in self._connections.values()
                if c.status in ("PENDING", "UNREACHABLE")
                   and (ts_ns - c.last_probe_ns) > 300_000_000_000  # 5 min cool-down
            ]
        if not pending:
            return
        # Pick the next one in rotation
        target = pending[self._probe_seq % len(pending)]
        self._probe_one(target, ts_ns)

    def _probe_one(self, conn: PlatformConnection, ts_ns: int) -> None:
        """Run api_sniffer against one platform (non-blocking thread)."""
        def _run() -> None:
            name = conn.platform.name
            url = conn.platform.base_url
            with self._lock:
                conn.status = "PROBING"
                conn.last_probe_ns = ts_ns
            try:
                from mind.sources.providers.api_sniffer import propose_candidate
                candidate = propose_candidate(url, emit_ledger=False)
                new_status = "CONNECTED" if candidate.relevance_score >= 0.3 else "UNREACHABLE"
                with self._lock:
                    conn.status = new_status
                    conn.api_surfaces = list(candidate.api_surfaces)
                    conn.relevance_score = candidate.relevance_score
                self._emit_discovery(name, url, new_status, candidate.relevance_score, ts_ns)
            except Exception as exc:
                with self._lock:
                    conn.status = "UNREACHABLE"
                    conn.error = str(exc)[:120]
        threading.Thread(target=_run, daemon=True, name=f"indira-probe-{conn.platform.name}").start()

    # ------------------------------------------------------------------
    # Research cycle — enqueue discovery topics into AutonomousResearchRuntime
    # ------------------------------------------------------------------

    def research_cycle(self, *, ts_ns: int) -> None:
        """Enqueue one backtesting discovery topic per call."""
        self._research_seq += 1
        topic_str = _RESEARCH_TOPICS[self._research_seq % len(_RESEARCH_TOPICS)]
        try:
            from intelligence_engine.research.autonomous_research_runtime import (
                AutonomousResearchRuntime, ResearchTopic, get_research_runtime,
            )
            from intelligence_engine.research.browser_research_service import ResearchTaskType
            rt = get_research_runtime()
            if not rt._running:
                rt.start()
            rt.enqueue(ResearchTopic(
                topic=topic_str,
                task_type=ResearchTaskType.MARKET_ANALYSIS,
                priority=7,
                ts_ns=ts_ns,
            ))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Add a newly discovered platform URL (from research results)
    # ------------------------------------------------------------------

    def add_candidate(self, url: str, source: str, ts_ns: int) -> None:
        """Register a newly discovered backtesting platform URL for probing."""
        if not url:
            return
        try:
            from urllib.parse import urlparse
            host = urlparse(url).netloc.lower().lstrip("www.")
        except Exception:
            host = url[:40]
        name = f"discovered_{host}"
        with self._lock:
            if name in self._connections:
                return
            platform = BacktestPlatform(
                name=name,
                base_url=url,
                api_kind="rest",
                capabilities=("backtest",),
                auth_type="none",
                trust_score=0.50,
                notes=f"auto-discovered via {source}",
            )
            self._connections[name] = PlatformConnection(platform=platform)

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def get_connected(self) -> list[PlatformConnection]:
        with self._lock:
            return [c for c in self._connections.values() if c.status == "CONNECTED"]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            conns = list(self._connections.values())
        by_status: dict[str, int] = {}
        for c in conns:
            by_status[c.status] = by_status.get(c.status, 0) + 1
        return {
            "total_platforms": len(conns),
            "by_status": by_status,
            "connected": [c.platform.name for c in conns if c.status == "CONNECTED"],
            "probe_seq": self._probe_seq,
            "research_seq": self._research_seq,
        }

    # ------------------------------------------------------------------
    # Cognitive emission
    # ------------------------------------------------------------------

    @staticmethod
    def _emit_discovery(name: str, url: str, status: str, score: float, ts_ns: int) -> None:
        try:
            from intelligence_engine.cognitive.observability_emitter import (
                emit_research_discovery,
            )
            emit_research_discovery(
                ts_ns=ts_ns,
                topic=f"backtesting_platform:{name}",
                source_url=url,
                summary=f"{name} probe → {status} (relevance {score:.2f})",
                confidence=score,
                trust_score=score,
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_registry: PlatformRegistry | None = None


def get_platform_registry() -> PlatformRegistry:
    """Return the module-level singleton PlatformRegistry."""
    global _registry
    if _registry is None:
        _registry = PlatformRegistry()
    return _registry


__all__ = [
    "BacktestPlatform",
    "PlatformConnection",
    "PlatformRegistry",
    "get_platform_registry",
]
