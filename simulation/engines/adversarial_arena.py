"""simulation.engines.adversarial_arena — Adversarial Trader Arena (Stage 8).

Five adversarial agent archetypes battle the target strategy each tick:

  FRONTRUNNER        — detects order direction, jumps queue ahead of target
  SPOOFER            — places and cancels large orders to move price
  WHALE_ACCUMULATOR  — slow-drip accumulation, minimal footprint
  STOP_HUNTER        — probes for stop-loss clusters, triggers cascade
  DARK_POOL_SHARK    — absorbs institutional flow in dark venues, prints late

Each agent maintains a running fitness score. The arena tracks survival
rate of the target strategy against all five agents in parallel.
"""
from __future__ import annotations

import dataclasses
import random
import threading
from collections import deque
from typing import Any


@dataclasses.dataclass(frozen=True, slots=True)
class AgentAction:
    ts_ns:      int
    agent_type: str
    action:     str
    target_won: bool
    edge_bps:   float   # edge extracted (basis points)


@dataclasses.dataclass(frozen=True, slots=True)
class AgentRecord:
    agent_type:    str
    wins:          int
    losses:        int
    total_edge_bps: float
    win_rate:      float
    last_action:   str


class _AdversarialAgent:
    """Base adversarial agent."""
    def __init__(self, agent_type: str, edge_mu: float, edge_sigma: float,
                 base_win_rate: float, rng: random.Random) -> None:
        self.agent_type    = agent_type
        self._edge_mu      = edge_mu
        self._edge_sigma   = edge_sigma
        self._base_win_rate = base_win_rate
        self._rng          = rng
        self.wins          = 0
        self.losses        = 0
        self.total_edge    = 0.0
        self.last_action   = "IDLE"

    def run(self, ts_ns: int, market_vol: float) -> AgentAction:
        # Win prob increases with market volatility (adversarial edge)
        win_prob = min(0.85, self._base_win_rate + market_vol * 2.0)
        won      = self._rng.random() < win_prob
        edge     = abs(self._rng.gauss(self._edge_mu, self._edge_sigma))

        if won:
            self.wins       += 1
            self.total_edge += edge
            self.last_action = self._win_action()
        else:
            self.losses     += 1
            self.last_action = self._lose_action()

        return AgentAction(
            ts_ns      = ts_ns,
            agent_type = self.agent_type,
            action     = self.last_action,
            target_won = not won,
            edge_bps   = round(edge if won else 0.0, 3),
        )

    def _win_action(self) -> str:  # pragma: no cover
        return "WIN"

    def _lose_action(self) -> str:  # pragma: no cover
        return "DETECTED"

    def record(self) -> AgentRecord:
        total = self.wins + self.losses
        return AgentRecord(
            agent_type     = self.agent_type,
            wins           = self.wins,
            losses         = self.losses,
            total_edge_bps = round(self.total_edge, 3),
            win_rate       = round(self.wins / max(1, total), 4),
            last_action    = self.last_action,
        )


class _Frontrunner(_AdversarialAgent):
    _ACTIONS_WIN  = ["JUMPED_QUEUE", "FILLED_AHEAD", "LATENCY_ADVANTAGE"]
    _ACTIONS_LOSE = ["QUEUE_MISSED", "SLIPPED_BACK", "DETECTED_HFT_FILTER"]

    def __init__(self, rng: random.Random) -> None:
        super().__init__("FRONTRUNNER", edge_mu=4.0, edge_sigma=2.0,
                         base_win_rate=0.52, rng=rng)

    def _win_action(self)  -> str: return self._rng.choice(self._ACTIONS_WIN)
    def _lose_action(self) -> str: return self._rng.choice(self._ACTIONS_LOSE)


class _Spoofer(_AdversarialAgent):
    _ACTIONS_WIN  = ["SPOOFED_BID_WALL", "SPOOFED_ASK_WALL", "PAINTED_TAPE"]
    _ACTIONS_LOSE = ["ORDER_CANCELLED_DETECTED", "EXCHANGE_FLAGGED", "REVERSED_PRICE"]

    def __init__(self, rng: random.Random) -> None:
        super().__init__("SPOOFER", edge_mu=6.0, edge_sigma=3.0,
                         base_win_rate=0.45, rng=rng)

    def _win_action(self)  -> str: return self._rng.choice(self._ACTIONS_WIN)
    def _lose_action(self) -> str: return self._rng.choice(self._ACTIONS_LOSE)


class _WhaleAccumulator(_AdversarialAgent):
    _ACTIONS_WIN  = ["DRIP_ACCUMULATED", "FOOTPRINT_HIDDEN", "DARK_POOL_CROSSED"]
    _ACTIONS_LOSE = ["FOOTPRINT_EXPOSED", "PRICE_IMPACT_EXCEEDED", "FLOW_DETECTED"]

    def __init__(self, rng: random.Random) -> None:
        super().__init__("WHALE_ACCUMULATOR", edge_mu=8.0, edge_sigma=4.0,
                         base_win_rate=0.40, rng=rng)

    def _win_action(self)  -> str: return self._rng.choice(self._ACTIONS_WIN)
    def _lose_action(self) -> str: return self._rng.choice(self._ACTIONS_LOSE)


class _StopHunter(_AdversarialAgent):
    _ACTIONS_WIN  = ["STOP_CLUSTER_HIT", "FORCED_LIQUIDATION", "SQUEEZE_TRIGGERED"]
    _ACTIONS_LOSE = ["STOPS_DEFENDED", "NO_CLUSTER_FOUND", "BOUNCED_EARLY"]

    def __init__(self, rng: random.Random) -> None:
        super().__init__("STOP_HUNTER", edge_mu=10.0, edge_sigma=5.0,
                         base_win_rate=0.38, rng=rng)

    def _win_action(self)  -> str: return self._rng.choice(self._ACTIONS_WIN)
    def _lose_action(self) -> str: return self._rng.choice(self._ACTIONS_LOSE)


class _DarkPoolShark(_AdversarialAgent):
    _ACTIONS_WIN  = ["ABSORBED_FLOW", "LATE_PRINT_ADVANTAGE", "INFORMED_CROSS"]
    _ACTIONS_LOSE = ["FLOW_AVOIDED", "ADVERSE_FILL", "VENUE_REJECTED"]

    def __init__(self, rng: random.Random) -> None:
        super().__init__("DARK_POOL_SHARK", edge_mu=5.0, edge_sigma=2.5,
                         base_win_rate=0.48, rng=rng)

    def _win_action(self)  -> str: return self._rng.choice(self._ACTIONS_WIN)
    def _lose_action(self) -> str: return self._rng.choice(self._ACTIONS_LOSE)


class AdversarialTraderArena:
    """Runs all 5 adversarial agents each tick and tracks strategy survival."""

    def __init__(self, seed: int = 99) -> None:
        rng = random.Random(seed)
        self._agents: list[_AdversarialAgent] = [
            _Frontrunner(random.Random(rng.getrandbits(32))),
            _Spoofer(random.Random(rng.getrandbits(32))),
            _WhaleAccumulator(random.Random(rng.getrandbits(32))),
            _StopHunter(random.Random(rng.getrandbits(32))),
            _DarkPoolShark(random.Random(rng.getrandbits(32))),
        ]
        self._recent: deque[AgentAction] = deque(maxlen=100)
        self._target_survived    = 0
        self._target_defeated    = 0
        self._tick_count         = 0
        self._lock               = threading.Lock()

    # ------------------------------------------------------------------
    def tick(self, ts_ns: int, market_vol: float = 0.02) -> None:
        try:
            with self._lock:
                self._tick_count += 1
                all_won = True
                for agent in self._agents:
                    action = agent.run(ts_ns, market_vol)
                    self._recent.append(action)
                    if not action.target_won:
                        all_won = False
                if all_won:
                    self._target_survived += 1
                else:
                    self._target_defeated += 1
        except Exception:
            pass

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            records = [a.record() for a in self._agents]
            recent  = [dataclasses.asdict(r) for r in list(self._recent)[-20:]]
            total   = self._target_survived + self._target_defeated
            survival_rate = self._target_survived / max(1, total)
            ticks   = self._tick_count
            surv    = self._target_survived
            defeat  = self._target_defeated

        leaderboard = sorted(
            [dataclasses.asdict(r) for r in records],
            key=lambda x: x["win_rate"], reverse=True,
        )
        return {
            "tick_count":       ticks,
            "target_survived":  surv,
            "target_defeated":  defeat,
            "survival_rate":    round(survival_rate, 4),
            "leaderboard":      leaderboard,
            "recent_actions":   recent,
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_singleton: AdversarialTraderArena | None = None
_lock = threading.Lock()


def get_adversarial_arena() -> AdversarialTraderArena:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = AdversarialTraderArena()
    return _singleton


__all__ = ["AdversarialTraderArena", "AgentRecord", "AgentAction",
           "get_adversarial_arena"]
