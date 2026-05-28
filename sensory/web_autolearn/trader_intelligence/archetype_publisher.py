"""TI-ING-05 — trader archetype publisher.

Publishes validated trader archetypes to the knowledge store.
Does NOT construct bus events (B27/B28). Returns payload dicts only.
INV-15. B1.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

__all__ = ["ArchetypeRecord", "ArchetypePublisher"]


@dataclass(frozen=True, slots=True)
class ArchetypeRecord:
    source_id: str
    ts_ns: int
    handle: str
    archetype: str
    credibility_score: float
    behavior_summary: dict[str, Any]
    content_hash: str


def _content_hash(source_id: str, archetype: str, ts_ns: int) -> str:
    raw = f"{source_id}:{archetype}:{ts_ns}".encode()
    return hashlib.blake2b(raw, digest_size=16).hexdigest()


class ArchetypePublisher:
    """Assembles ArchetypeRecord and publishes to a caller-supplied sink.

    sink: Callable[[ArchetypeRecord], None] — e.g. knowledge_store.upsert
    """

    def __init__(self, sink: Any) -> None:
        self._sink = sink

    def publish(
        self,
        *,
        source_id: str,
        ts_ns: int,
        handle: str,
        archetype: str,
        credibility_score: float,
        activity_level: str,
        sentiment_bias: str,
        archetype_scores: tuple[tuple[str, float], ...],
    ) -> ArchetypeRecord:
        record = ArchetypeRecord(
            source_id=source_id,
            ts_ns=ts_ns,
            handle=handle,
            archetype=archetype,
            credibility_score=credibility_score,
            behavior_summary={
                "activity_level": activity_level,
                "sentiment_bias": sentiment_bias,
                "archetype_scores": dict(archetype_scores),
            },
            content_hash=_content_hash(source_id, archetype, ts_ns),
        )
        self._sink(record)
        return record
