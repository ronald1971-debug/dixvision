"""TraderIntelligenceRuntime — live archetype evaluation loop (P1 Evolution Infrastructure).

Closes the Trader Intelligence pipeline:
  seed_traders.py → style params → ArchetypeArena
  → regime-adjusted matches → top archetype → INDIRA_INSIGHT event

On activation:
  - Seeds the ArchetypeArena from mind.knowledge.seed_traders (curated roster).
  - Maps each trader's style to quantitative behavior params.

On each tick():
  - Reads current market regime from MarketState.
  - Applies regime multipliers to archetype params (BULL/BEAR/MIXED).
  - Runs a round of arena matches.
  - Publishes INDIRA_INSIGHT when the top archetype changes.

Authority (B1): intelligence_engine.*, mind.*, state.*, core.* only.
INV-15: ts_ns is caller-supplied; no wall-clock reads.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Style → base behavior params
# ---------------------------------------------------------------------------

_STYLE_PARAMS: dict[str, dict[str, float]] = {
    "classical": {
        "trend_following": 0.70, "discretionary": 0.80, "patience": 0.90,
        "risk_management": 0.70,
    },
    "value": {
        "value": 0.90, "mean_reversion": 0.60, "patience": 0.95,
        "contrarian": 0.70, "risk_management": 0.75,
    },
    "macro": {
        "macro_awareness": 0.90, "trend_following": 0.60, "patience": 0.75,
        "regime_sensitivity": 0.85, "discretionary": 0.70,
    },
    "quant": {
        "systematic": 0.90, "quant": 0.90, "risk_management": 0.85,
        "speed": 0.60, "trend_following": 0.50,
    },
    "crypto": {
        "momentum": 0.80, "risk_tolerance": 0.85, "speed": 0.70,
        "contrarian": 0.40, "regime_sensitivity": 0.60,
    },
    "hft": {
        "speed": 0.95, "systematic": 0.90, "quant": 0.85,
        "risk_management": 0.75, "momentum": 0.50,
    },
    "technical": {
        "trend_following": 0.80, "systematic": 0.70, "momentum": 0.65,
        "patience": 0.60, "risk_management": 0.65,
    },
    "growth": {
        "momentum": 0.75, "trend_following": 0.65, "patience": 0.70,
        "risk_tolerance": 0.65, "contrarian": 0.30,
    },
    "global_macro": {
        "macro_awareness": 0.95, "regime_sensitivity": 0.90, "patience": 0.80,
        "risk_management": 0.80, "discretionary": 0.75,
    },
}

# ---------------------------------------------------------------------------
# Regime multipliers applied on top of base params before each match round
# ---------------------------------------------------------------------------

_REGIME_MULTIPLIERS: dict[str, dict[str, float]] = {
    "BULL": {
        "trend_following": 1.40, "momentum": 1.30, "risk_tolerance": 1.20,
        "systematic": 1.10, "mean_reversion": 0.70,
    },
    "BEAR": {
        "mean_reversion": 1.50, "value": 1.35, "macro_awareness": 1.25,
        "risk_management": 1.40, "contrarian": 1.20, "momentum": 0.70,
    },
    "MIXED": {
        "quant": 1.30, "macro_awareness": 1.20, "systematic": 1.20,
        "discretionary": 1.10, "regime_sensitivity": 1.15,
    },
}

# How many arena matches to run per tick
_MATCHES_PER_TICK = 4


# ---------------------------------------------------------------------------
# TraderIntelligenceRuntime
# ---------------------------------------------------------------------------


class TraderIntelligenceRuntime:
    """Orchestrates the trader archetype evaluation loop.

    Args:
        tick_interval: Run a match round every N ticks (default 50).
    """

    def __init__(self, *, tick_interval: int = 50) -> None:
        self._lock = threading.Lock()
        self._tick_count = 0
        self._tick_interval = max(1, tick_interval)
        self._match_rounds = 0
        self._seeded = False
        self._top_archetype: str = ""
        self._top_win_rate: float = 0.0
        self._archetype_ids: list[str] = []
        self._archetype_base_params: dict[str, dict[str, float]] = {}

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Seed archetypes from the curated roster.  Idempotent."""
        with self._lock:
            if self._seeded:
                return
        self._seed_archetypes()
        with self._lock:
            self._seeded = True
        _logger.info(
            "TraderIntelligenceRuntime: seeded %d archetypes",
            len(self._archetype_ids),
        )

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def tick(self, *, ts_ns: int) -> bool:
        """Advance one tick; run match round if interval fires.

        Returns True if a match round ran this tick.
        """
        with self._lock:
            self._tick_count += 1
            should_run = self._tick_count % self._tick_interval == 0
            seeded = self._seeded

        if not seeded:
            self.activate()

        if not should_run:
            return False

        self._run_match_round(ts_ns=ts_ns)
        return True

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        try:
            from intelligence_engine.meta.archetype_arena import get_archetype_arena
            arena_snap = get_archetype_arena().snapshot()
        except Exception:
            arena_snap = {}
        with self._lock:
            return {
                "tick_count": self._tick_count,
                "match_rounds": self._match_rounds,
                "seeded": self._seeded,
                "archetype_count": len(self._archetype_ids),
                "top_archetype": self._top_archetype,
                "top_win_rate": round(self._top_win_rate, 3),
                "arena": arena_snap,
            }

    def format_for_context(self) -> str:
        """Compact archetype context string for INDIRA injection."""
        with self._lock:
            if not self._top_archetype:
                return ""
            return f"top_archetype={self._top_archetype} win_rate={self._top_win_rate:.0%}"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _seed_archetypes(self) -> None:
        """Load seed traders and register them in the arena."""
        try:
            from intelligence_engine.meta.archetype_arena import get_archetype_arena
            from mind.knowledge.seed_traders import _SEED
            arena = get_archetype_arena()
            ids: list[str] = []
            base_params: dict[str, dict[str, float]] = {}
            for trader in _SEED:
                archetype_id = self._trader_id(trader.name)
                params = self._style_to_params(trader.style, trader.strategies)
                arena.register_archetype(archetype_id, params)
                ids.append(archetype_id)
                base_params[archetype_id] = params
            with self._lock:
                self._archetype_ids = ids
                self._archetype_base_params = base_params
        except Exception as exc:
            _logger.debug("TraderIntelligenceRuntime._seed_archetypes error: %s", exc)

    def _run_match_round(self, *, ts_ns: int) -> None:
        """Run a batch of arena matches in the current regime."""
        try:
            from intelligence_engine.meta.archetype_arena import get_archetype_arena
            arena = get_archetype_arena()

            regime = self._current_regime()
            ids = list(self._archetype_ids)
            if len(ids) < 2:
                return

            # Apply regime multipliers to all archetypes for this round
            with self._lock:
                base_params_snap = dict(self._archetype_base_params)
                match_rounds = self._match_rounds
            multipliers = _REGIME_MULTIPLIERS.get(regime, {})
            for aid in ids:
                base = base_params_snap.get(aid, {})
                if base and multipliers:
                    adjusted = {
                        k: min(1.0, v * multipliers.get(k, 1.0))
                        for k, v in base.items()
                    }
                    arena.register_archetype(aid, adjusted)

            # Round-robin pairs — offset by match_rounds so different pairs each round
            pairs = self._pick_pairs(ids, n=_MATCHES_PER_TICK, offset=match_rounds)
            for a, b in pairs:
                try:
                    arena.run_match(a, b, regime=regime, ts_ns=ts_ns)
                except Exception:
                    pass

            with self._lock:
                self._match_rounds += 1

            # Check if leaderboard top changed
            board = arena.leaderboard()
            if board:
                new_top, new_rate = board[0]
                with self._lock:
                    changed = (new_top != self._top_archetype)
                    self._top_archetype = new_top
                    self._top_win_rate = new_rate
                if changed:
                    self._publish_insight(new_top, new_rate, regime, ts_ns)

        except Exception as exc:
            _logger.debug("TraderIntelligenceRuntime._run_match_round error: %s", exc)

    def _current_regime(self) -> str:
        """Read the current market regime from MarketState.  Fallback: MIXED."""
        try:
            from state.market_state import get_market_state
            return get_market_state().regime()
        except Exception:
            return "MIXED"

    @staticmethod
    def _publish_insight(top: str, win_rate: float, regime: str, ts_ns: int) -> None:
        """Publish new top archetype as an INDIRA_INSIGHT event."""
        try:
            from state.event_bus import CognitiveChannel, get_event_bus
            get_event_bus().publish(CognitiveChannel.INDIRA_INSIGHT, {
                "subject": "TOP_TRADER_ARCHETYPE",
                "body": f"Dominant archetype: {top} (win_rate={win_rate:.0%}, regime={regime})",
                "confidence": min(1.0, win_rate + 0.1),
                "evidence_count": 1,
                "ts_ns": ts_ns,
            })
        except Exception:
            pass

    @staticmethod
    def _trader_id(name: str) -> str:
        return name.lower().replace(" ", "_").replace(".", "").replace(",", "")[:32]

    @staticmethod
    def _style_to_params(style: str, strategies: tuple[str, ...]) -> dict[str, float]:
        """Derive base params from style + strategy tags."""
        base = dict(_STYLE_PARAMS.get(style, _STYLE_PARAMS.get("classical", {})))
        # Boost params from strategy tags
        if "trend_following" in strategies:
            base["trend_following"] = min(1.0, base.get("trend_following", 0.5) + 0.15)
        if "mean_reversion" in strategies:
            base["mean_reversion"] = min(1.0, base.get("mean_reversion", 0.5) + 0.15)
        if any("quant" in s or "systematic" in s for s in strategies):
            base["systematic"] = min(1.0, base.get("systematic", 0.5) + 0.10)
        if any("risk" in s for s in strategies):
            base["risk_management"] = min(1.0, base.get("risk_management", 0.5) + 0.10)
        return base

    @staticmethod
    def _pick_pairs(ids: list[str], n: int, offset: int = 0) -> list[tuple[str, str]]:
        """Pick n deterministic sequential pairs, offset by round number (INV-15)."""
        pairs: list[tuple[str, str]] = []
        total = len(ids)
        if total < 2:
            return pairs
        for i in range(n):
            a = ids[(offset + i) % total]
            b = ids[(offset + i + 1) % total]
            if a != b:
                pairs.append((a, b))
        return pairs


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_runtime: TraderIntelligenceRuntime | None = None
_runtime_lock = threading.Lock()


def get_trader_intelligence_runtime(*, tick_interval: int = 50) -> TraderIntelligenceRuntime:
    """Return the process-wide TraderIntelligenceRuntime singleton."""
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = TraderIntelligenceRuntime(tick_interval=tick_interval)
    return _runtime


__all__ = [
    "TraderIntelligenceRuntime",
    "get_trader_intelligence_runtime",
]
