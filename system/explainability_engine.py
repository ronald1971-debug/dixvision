"""system.explainability_engine — decision explainability store.

Records human-readable rationales for system decisions (trade signals,
governance votes, hazard triggers) so the cockpit can display "why did
the system do X?" without replaying the full audit ledger.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Explanation:
    decision_id: str
    decision_kind: str
    rationale: str
    confidence: float
    ts_ns: int
    source: str = ""


class ExplainabilityEngine:
    """Bounded ring buffer of recent decision explanations."""

    _MAX_ENTRIES = 500

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: deque[Explanation] = deque(maxlen=self._MAX_ENTRIES)

    def record(self, explanation: Explanation) -> None:
        with self._lock:
            self._entries.append(explanation)

    def recent(self, n: int = 20) -> list[Explanation]:
        with self._lock:
            return list(self._entries)[-n:]

    def by_kind(self, decision_kind: str, n: int = 20) -> list[Explanation]:
        with self._lock:
            matches = [e for e in self._entries if e.decision_kind == decision_kind]
            return matches[-n:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"total_explanations": len(self._entries)}


_engine: ExplainabilityEngine | None = None
_lock = threading.Lock()


def get_explainability_engine() -> ExplainabilityEngine:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = ExplainabilityEngine()
    return _engine
