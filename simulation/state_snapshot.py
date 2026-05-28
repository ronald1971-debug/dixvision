"""simulation/state_snapshot.py
DIX VISION v42.2 — Simulation State Snapshot

Captures and restores complete simulation state at checkpoints.
Enables branching simulation runs (fork-and-compare), crash recovery,
and deterministic replay of simulation episodes.

Thread-safe. Frozen dataclasses (INV-15).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time as _time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PositionState:
    """Open position state within a simulation."""
    symbol: str
    side: str
    qty: float
    entry_price: float
    unrealised_pnl: float
    entry_ts_ns: int


@dataclass(frozen=True, slots=True)
class SimulationStateSnapshot:
    """Complete simulation state at a checkpoint."""
    snapshot_id: str
    strategy_id: str
    scenario_id: str
    bar_index: int
    ts_ns: int
    cash_usd: float
    equity_usd: float
    positions: tuple[PositionState, ...]
    realised_pnl: float
    num_trades: int
    checksum: str    # deterministic hash of state fields (INV-15)

    @property
    def total_position_value(self) -> float:
        return sum(p.qty * p.entry_price for p in self.positions)


def _compute_checksum(
    strategy_id: str,
    scenario_id: str,
    bar_index: int,
    cash_usd: float,
    positions: tuple[PositionState, ...],
    realised_pnl: float,
) -> str:
    """Deterministic checksum for state fields (INV-15)."""
    pos_repr = "|".join(
        f"{p.symbol}:{p.side}:{p.qty}:{p.entry_price}"
        for p in sorted(positions, key=lambda x: x.symbol)
    )
    canonical = f"{strategy_id}|{scenario_id}|{bar_index}|{cash_usd:.8f}|{pos_repr}|{realised_pnl:.8f}"
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def create_snapshot(
    strategy_id: str,
    scenario_id: str,
    bar_index: int,
    ts_ns: int,
    cash_usd: float,
    equity_usd: float,
    positions: list[PositionState],
    realised_pnl: float,
    num_trades: int,
) -> SimulationStateSnapshot:
    pos_tuple = tuple(sorted(positions, key=lambda p: p.symbol))
    checksum = _compute_checksum(
        strategy_id, scenario_id, bar_index, cash_usd, pos_tuple, realised_pnl
    )
    return SimulationStateSnapshot(
        snapshot_id=str(uuid.uuid4()),
        strategy_id=strategy_id,
        scenario_id=scenario_id,
        bar_index=bar_index,
        ts_ns=ts_ns,
        cash_usd=cash_usd,
        equity_usd=equity_usd,
        positions=pos_tuple,
        realised_pnl=realised_pnl,
        num_trades=num_trades,
        checksum=checksum,
    )


class SnapshotStore:
    """
    Thread-safe in-memory store for simulation state snapshots.

    Supports checkpoint-based branching: fork() returns a copy of
    the snapshot that can be evolved independently.
    """

    def __init__(self, max_snapshots: int = 100) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, SimulationStateSnapshot] = {}
        self._max = max_snapshots

    def save(self, snapshot: SimulationStateSnapshot) -> None:
        with self._lock:
            self._store[snapshot.snapshot_id] = snapshot
            while len(self._store) > self._max:
                oldest = next(iter(self._store))
                del self._store[oldest]

    def load(self, snapshot_id: str) -> SimulationStateSnapshot | None:
        with self._lock:
            return self._store.get(snapshot_id)

    def latest_for(self, strategy_id: str) -> SimulationStateSnapshot | None:
        with self._lock:
            candidates = [
                s for s in self._store.values()
                if s.strategy_id == strategy_id
            ]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.bar_index)

    def verify_checksum(self, snapshot: SimulationStateSnapshot) -> bool:
        expected = _compute_checksum(
            snapshot.strategy_id,
            snapshot.scenario_id,
            snapshot.bar_index,
            snapshot.cash_usd,
            snapshot.positions,
            snapshot.realised_pnl,
        )
        return snapshot.checksum == expected

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"stored": len(self._store)}


__all__ = [
    "PositionState",
    "SimulationStateSnapshot",
    "SnapshotStore",
    "create_snapshot",
]
