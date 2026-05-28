"""system.state_persistence — system state checkpoint and restore.

Writes periodic snapshots of system state to a JSON file so the system
can warm-start without replaying the full ledger. Not authoritative —
the append-only ledger remains the source of truth; this is a
performance optimisation for fast restarts.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


_DEFAULT_PATH = Path("data") / "system_state.json"


class StatePersistence:
    """Serialise and deserialise system state to a local JSON checkpoint."""

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()

    def save(self, state_dict: dict[str, Any]) -> None:
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._path.write_text(json.dumps(state_dict, indent=2), encoding="utf-8")
            except OSError:
                pass

    def load(self) -> dict[str, Any] | None:
        with self._lock:
            try:
                if not self._path.exists():
                    return None
                return json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None

    def clear(self) -> None:
        with self._lock:
            try:
                self._path.unlink(missing_ok=True)
            except OSError:
                pass


_persistence: StatePersistence | None = None
_lock = threading.Lock()


def get_state_persistence(path: Path = _DEFAULT_PATH) -> StatePersistence:
    global _persistence
    if _persistence is None:
        with _lock:
            if _persistence is None:
                _persistence = StatePersistence(path=path)
    return _persistence
