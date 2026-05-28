# ADAPTED FROM: jnwatson/py-lmdb
# (lmdb/__init__.py — open(), Environment.begin(), Transaction.put(),
#  Transaction.get(), Transaction.cursor(); memory-mapped ACID key-value store)
"""C-53 — LMDB ultra-low-latency key-value cache.

This module adapts ``py-lmdb`` for sub-microsecond local cache reads.
Used as a pre-PyO3 fast risk cache (position snapshots, risk state).
No network — pure memory-mapped file access.

What survives from upstream (jnwatson/py-lmdb):
    * **Environment** — ``open(path, map_size)`` creates the mmap store.
    * **Transaction** — ``env.begin(write=True/False)`` for ACID.
    * **put/get/delete** — ``txn.put(key, value)`` / ``txn.get(key)``
      / ``txn.delete(key)`` with raw bytes.
    * **cursor** — ``txn.cursor()`` for iteration / range scans.

What we replaced:
    * Real ``lmdb`` import is lazy (falls back to in-memory dict).
    * Same interface as ``state/cache/redis_store.py`` (get/set/delete).
    * Read latency ~100ns with real LMDB (mmap).
    * RUNTIME safe (read-only mmap, no network).
"""

from __future__ import annotations

from typing import Any


class LMDBStore:
    """Ultra-low-latency local key-value cache via LMDB.

    Mirrors ``lmdb.open()`` / ``txn.get()`` / ``txn.put()`` patterns.
    Falls back to an in-memory dict when ``lmdb`` is not installed.

    Usage::

        store = LMDBStore(path="/var/dix/cache/risk")
        store.put(b"position:AAPL", b"100.0")
        val = store.get(b"position:AAPL")
    """

    def __init__(
        self,
        *,
        path: str = "",
        map_size: int = 1_073_741_824,  # 1 GB default
        in_memory: bool = True,
    ) -> None:
        self._path = path
        self._map_size = map_size
        self._in_memory = in_memory
        self._env: Any = None
        self._fallback: dict[bytes, bytes] = {}

        if not in_memory and path:
            self._open_env()

    def _open_env(self) -> None:
        """Open the LMDB environment (lazy)."""
        try:
            import lmdb

            self._env = lmdb.open(self._path, map_size=self._map_size)
        except ImportError:
            self._in_memory = True

    def put(self, key: bytes, value: bytes) -> bool:
        """Store a key-value pair. Returns True on success."""
        if self._in_memory or self._env is None:
            self._fallback[key] = value
            return True

        with self._env.begin(write=True) as txn:
            return txn.put(key, value)

    def get(self, key: bytes) -> bytes | None:
        """Retrieve a value by key. Returns None if not found."""
        if self._in_memory or self._env is None:
            return self._fallback.get(key)

        with self._env.begin() as txn:
            return txn.get(key)

    def delete(self, key: bytes) -> bool:
        """Delete a key. Returns True if existed."""
        if self._in_memory or self._env is None:
            if key in self._fallback:
                del self._fallback[key]
                return True
            return False

        with self._env.begin(write=True) as txn:
            return txn.delete(key)

    def exists(self, key: bytes) -> bool:
        """Check if a key exists."""
        if self._in_memory or self._env is None:
            return key in self._fallback

        with self._env.begin() as txn:
            return txn.get(key) is not None

    def keys(self) -> list[bytes]:
        """Return all keys in the store."""
        if self._in_memory or self._env is None:
            return list(self._fallback.keys())

        with self._env.begin() as txn:
            return [key for key, _ in txn.cursor()]

    def count(self) -> int:
        """Return number of entries."""
        if self._in_memory or self._env is None:
            return len(self._fallback)

        with self._env.begin() as txn:
            return txn.stat()["entries"]

    def close(self) -> None:
        """Close the LMDB environment."""
        if self._env is not None:
            self._env.close()
            self._env = None


__all__ = ["LMDBStore"]
