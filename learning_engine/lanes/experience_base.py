"""learning_engine/lanes/experience_base.py
DIX VISION v42.2 — Experience Base (replay buffer)

Provides a bounded experience buffer for reinforcement / continual
learning. Stores (state, action, reward, next_state, done) tuples
as ExperienceRecord frozen dataclasses.

Supports uniform random sampling and priority-weighted sampling
(proportional to |reward|). Thread-safe. Pure data — no IO, no
clock reads in core logic (INV-15).
"""

from __future__ import annotations

import math
import random
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ExperienceRecord:
    """One (s, a, r, s', done) transition tuple."""
    record_id: str
    strategy_id: str
    state: tuple[float, ...]
    action: tuple[float, ...]
    reward: float
    next_state: tuple[float, ...]
    done: bool
    ts_ns: int
    meta: dict[str, str]


class ExperienceBase:
    """
    Bounded experience replay buffer.

    Thread-safe. Stores at most ``capacity`` records; oldest records
    are evicted when capacity is reached.
    """

    def __init__(self, capacity: int = 10_000) -> None:
        self._capacity = capacity
        self._lock = threading.Lock()
        self._buffer: deque[ExperienceRecord] = deque(maxlen=capacity)

    def add(self, record: ExperienceRecord) -> None:
        with self._lock:
            self._buffer.append(record)

    def sample_uniform(self, n: int) -> list[ExperienceRecord]:
        """Return up to n records sampled uniformly at random."""
        with self._lock:
            buf = list(self._buffer)
        if not buf:
            return []
        return random.sample(buf, min(n, len(buf)))

    def sample_priority(self, n: int) -> list[ExperienceRecord]:
        """Return up to n records sampled proportionally to |reward|."""
        with self._lock:
            buf = list(self._buffer)
        if not buf:
            return []
        weights = [max(abs(r.reward), 1e-8) for r in buf]
        total = sum(weights)
        probs = [w / total for w in weights]
        k = min(n, len(buf))
        indices = random.choices(range(len(buf)), weights=probs, k=k)
        seen: set[int] = set()
        result: list[ExperienceRecord] = []
        for idx in indices:
            if idx not in seen:
                seen.add(idx)
                result.append(buf[idx])
        return result

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "capacity": self._capacity,
                "size": len(self._buffer),
            }


# Singleton factory
_instance: ExperienceBase | None = None
_lock = threading.Lock()


def get_experience_base(capacity: int = 10_000) -> ExperienceBase:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ExperienceBase(capacity=capacity)
    return _instance


__all__ = ["ExperienceBase", "ExperienceRecord", "get_experience_base"]
