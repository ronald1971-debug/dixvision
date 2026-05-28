"""
security/secrets_manager.py
In-memory secret store backed by an optional dotenv file on disk.

On init, if ``DIX_SECRETS_PATH`` is set (or the default
``.dix_secrets.env`` exists), secrets are loaded from that file.
Every ``set()`` / ``delete()`` call writes back atomically so
credentials survive process restarts.

Production deployments can additionally back this by the Windows
Credential Manager (via keyring_adapter) or a cloud KMS.

Security invariants:
  - never write plaintext to ledger / logs
  - never leave the process address space (credentials_never_leave_machine)
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path


class SecretsManager:
    def __init__(self, dotenv_path: str | None = None) -> None:
        self._lock = threading.RLock()
        self._store: dict[str, str] = {}
        self._path: Path | None = None

        raw = dotenv_path or os.environ.get("DIX_SECRETS_PATH", "")
        if raw:
            self._path = Path(raw)
        else:
            candidate = Path(".dix_secrets.env")
            if candidate.exists():
                self._path = candidate

        if self._path is not None:
            self._load()

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            from system_engine.credentials.dotenv_io import load_dotenv_file

            self._store.update(load_dotenv_file(self._path))
        except Exception as exc:
            sys.stderr.write(f"[SecretsManager] load failed: {exc}\n")

    def _persist(self) -> None:
        if self._path is None:
            return
        try:
            from system_engine.credentials.dotenv_io import update_dotenv_file

            update_dotenv_file(self._path, self._store)
        except Exception as exc:
            sys.stderr.write(f"[SecretsManager] persist failed: {exc}\n")

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._store[key] = value
            self._persist()

    def get(self, key: str, default: str = "") -> str:
        with self._lock:
            return self._store.get(key, default)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)
            self._persist()

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._store.keys())


_sm: SecretsManager | None = None
_lock = threading.Lock()


def get_secrets_manager() -> SecretsManager:
    global _sm
    if _sm is None:
        with _lock:
            if _sm is None:
                _sm = SecretsManager()
    return _sm
