"""mind.sources.ai_knowledge_input — AI-generated knowledge provider.

Bridges the :mod:`intelligence_engine` advisory layer with the mind
source registry. External callers push :class:`AiKnowledgeItem` objects
into the collector; the provider's :meth:`poll` drains the queue so the
knowledge store can ingest AI-generated insights alongside market and
news streams.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AiKnowledgeItem:
    """One AI-generated insight fragment.

    Attributes:
        topic: Short category tag (e.g. ``"market_regime"``,
            ``"risk_signal"``, ``"strategy_critique"``).
        text: The natural-language insight text.
        confidence: Caller-assigned confidence in ``[0.0, 1.0]``.
        source: Identifier of the generating component.
        ts_ns: Caller-supplied timestamp (nanoseconds since epoch).
    """

    topic: str
    text: str
    confidence: float
    source: str
    ts_ns: int


class AiKnowledgeInput:
    """Thread-safe bounded queue of AI-generated knowledge items.

    Callers push items via :meth:`push`; the mind source registry
    drains them via :meth:`poll` on its normal polling cycle.
    """

    _MAX_QUEUE = 1_000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: deque[AiKnowledgeItem] = deque(maxlen=self._MAX_QUEUE)

    def push(self, item: AiKnowledgeItem) -> None:
        with self._lock:
            self._queue.append(item)

    def poll(self) -> list[AiKnowledgeItem]:
        """Drain and return all queued items."""
        with self._lock:
            items = list(self._queue)
            self._queue.clear()
            return items

    def pending(self) -> int:
        with self._lock:
            return len(self._queue)

    def snapshot(self) -> dict[str, Any]:
        return {"pending": self.pending()}


_input: AiKnowledgeInput | None = None
_lock = threading.Lock()


def get_ai_knowledge_input() -> AiKnowledgeInput:
    global _input
    if _input is None:
        with _lock:
            if _input is None:
                _input = AiKnowledgeInput()
    return _input
