"""system.causal_inference_engine — system-tier causal inference facade.

Thin coordinator that routes causal "did X cause Y?" queries to the
:mod:`intelligence_engine` causal adapter layer. Maintains a bounded
result cache keyed on the query digest so repeated identical queries
don't re-run expensive estimation passes.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CausalQuery:
    treatment: str
    outcome: str
    context: str = ""


@dataclass(frozen=True)
class CausalResult:
    query_digest: str
    treatment: str
    outcome: str
    effect_estimate: float
    confidence: float
    method: str
    notes: str = ""


class CausalInferenceEngine:
    """Bounded LRU cache and dispatch for system-tier causal queries."""

    _MAX_CACHE = 256

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, CausalResult] = {}

    def _digest(self, query: CausalQuery) -> str:
        raw = f"{query.treatment}|{query.outcome}|{query.context}".encode()
        return hashlib.blake2b(raw, digest_size=8).hexdigest()

    def lookup(self, query: CausalQuery) -> CausalResult | None:
        with self._lock:
            return self._cache.get(self._digest(query))

    def record(self, result: CausalResult) -> None:
        with self._lock:
            if len(self._cache) >= self._MAX_CACHE:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[result.query_digest] = result

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"cached_results": len(self._cache)}


_engine: CausalInferenceEngine | None = None
_lock = threading.Lock()


def get_causal_inference_engine() -> CausalInferenceEngine:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = CausalInferenceEngine()
    return _engine
