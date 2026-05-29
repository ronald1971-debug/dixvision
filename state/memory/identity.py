"""state.memory.identity — MemoryIdentitySystem.

Assigns stable, deterministic record_ids and deduplicates records
that arrive within a 60-second window with the same content fingerprint.

Rules:
- record_id = sha256(kind + source + summary + ts_bucket) where
  ts_bucket = ts_ns // 60_000_000_000  (60-second buckets)
- Fingerprint collision within the same bucket → dedup (return existing id)
- No IO, no clock reads (INV-15) — ts_ns is always caller-supplied.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state.memory.contracts import MemoryKind

_BUCKET_NS = 60_000_000_000          # 60 seconds in nanoseconds
_CACHE_MAX  = 4_096                   # max fingerprints in dedup cache


class MemoryIdentitySystem:
    """Assigns stable ids and deduplicates cognitive memory records."""

    def __init__(self) -> None:
        self._lock  = threading.Lock()
        self._seen:  OrderedDict[str, str] = OrderedDict()  # fp → record_id
        self._total: int = 0
        self._dedup: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assign(
        self,
        *,
        kind: "MemoryKind",
        source: str,
        summary: str,
        ts_ns: int,
    ) -> tuple[str, bool]:
        """Return (record_id, is_new).

        ``is_new`` is False when a record with the same fingerprint
        was already assigned within the same 60-second bucket.
        Callers should skip writing when ``is_new`` is False.
        """
        fp = self._fingerprint(kind, source, summary, ts_ns)
        with self._lock:
            if fp in self._seen:
                self._dedup += 1
                return self._seen[fp], False
            rid = self._make_id(kind, source, summary, ts_ns)
            self._seen[fp] = rid
            self._total += 1
            if len(self._seen) > _CACHE_MAX:
                self._seen.popitem(last=False)
        return rid, True

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active":      True,
                "total_issued": self._total,
                "dedup_hits":   self._dedup,
                "cache_size":   len(self._seen),
            }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _fingerprint(kind: "MemoryKind", source: str, summary: str, ts_ns: int) -> str:
        bucket = ts_ns // _BUCKET_NS
        raw    = f"{kind}|{source}|{summary}|{bucket}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _make_id(kind: "MemoryKind", source: str, summary: str, ts_ns: int) -> str:
        raw = f"{kind}|{source}|{summary}|{ts_ns}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
        return f"mem-{kind.value.lower()[:3]}-{digest}"


_singleton: MemoryIdentitySystem | None = None
_lock = threading.Lock()


def get_memory_identity_system() -> MemoryIdentitySystem:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = MemoryIdentitySystem()
    return _singleton


__all__ = ["MemoryIdentitySystem", "get_memory_identity_system"]
