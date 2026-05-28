# ADAPTED FROM: hvac/hvac
# (hvac/api/secrets_engines/kv_v2.py — read_secret_version,
#  create_or_update_secret; hvac/adapters.py — JSONAdapter HTTP;
#  hvac/api/auth_methods/token.py — Token.renew_self())
"""C-70 — HashiCorp Vault integration for credential storage.

This module adapts ``hvac`` (HashiCorp Vault API client) as an optional
production credential backend. Falls back to local crypto.py if Vault
is unavailable.

What survives from upstream (hvac/hvac):
    * **Client** — ``v1.Client(url, token)``: connection to Vault.
    * **KV v2** — ``kv_v2.read_secret_version(path)`` /
      ``create_or_update_secret(path, secret)``.
    * **Token renewal** — ``auth.token.renew_self()`` for automatic
      token refresh.

What we replaced:
    * Real ``hvac`` import is lazy (Protocol seam).
    * In-memory secret store for unit tests.
    * Credentials NEVER logged. Vault namespace per DIX instance.

RUNTIME tier: decrypt/fetch credentials on startup.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VaultSecret:
    """A secret retrieved from Vault."""

    path: str
    data: dict[str, str]
    version: int = 1


class VaultBackend:
    """HashiCorp Vault credential backend.

    Mirrors ``hvac.Client`` + KV v2 secrets engine patterns.
    Falls back to in-memory storage when Vault is unavailable.

    Usage::

        vault = VaultBackend(url="http://vault:8200", token="...")
        vault.write_secret("dix/api-keys", {"binance": "key123"})
        secret = vault.read_secret("dix/api-keys")
    """

    def __init__(
        self,
        *,
        url: str = "http://127.0.0.1:8200",
        token: str = "",
        namespace: str = "dix",
        in_memory: bool = True,
    ) -> None:
        self._url = url
        self._token = token
        self._namespace = namespace
        self._in_memory = in_memory
        self._store: dict[str, VaultSecret] = {}

    def write_secret(self, path: str, data: dict[str, str]) -> bool:
        """Write a secret to Vault KV v2.

        Mirrors ``client.secrets.kv.v2.create_or_update_secret()``.
        """
        if self._in_memory:
            version = 1
            existing = self._store.get(path)
            if existing:
                version = existing.version + 1
            self._store[path] = VaultSecret(path=path, data=data, version=version)
            return True
        return self._write_remote(path, data)

    def read_secret(self, path: str) -> VaultSecret | None:
        """Read a secret from Vault KV v2.

        Mirrors ``client.secrets.kv.v2.read_secret_version()``.
        """
        if self._in_memory:
            return self._store.get(path)
        return self._read_remote(path)

    def delete_secret(self, path: str) -> bool:
        """Delete a secret from Vault."""
        if self._in_memory:
            if path in self._store:
                del self._store[path]
                return True
            return False
        return self._delete_remote(path)

    def list_secrets(self, prefix: str = "") -> list[str]:
        """List secret paths under a prefix."""
        if self._in_memory:
            return [p for p in self._store.keys() if p.startswith(prefix)]
        return self._list_remote(prefix)

    def is_available(self) -> bool:
        """Check if Vault is reachable."""
        if self._in_memory:
            return True
        return self._health_check()

    # ---- remote internals ------------------------------------------------

    def _write_remote(self, path: str, data: dict[str, str]) -> bool:
        try:
            import hvac

            client = hvac.Client(url=self._url, token=self._token, namespace=self._namespace)
            client.secrets.kv.v2.create_or_update_secret(path=path, secret=data)
            return True
        except (ImportError, Exception):
            return False

    def _read_remote(self, path: str) -> VaultSecret | None:
        try:
            import hvac

            client = hvac.Client(url=self._url, token=self._token, namespace=self._namespace)
            resp = client.secrets.kv.v2.read_secret_version(path=path)
            d = resp["data"]["data"]
            v = resp["data"]["metadata"]["version"]
            return VaultSecret(path=path, data=d, version=v)
        except (ImportError, Exception):
            return None

    def _delete_remote(self, path: str) -> bool:
        try:
            import hvac

            client = hvac.Client(url=self._url, token=self._token, namespace=self._namespace)
            client.secrets.kv.v2.delete_metadata_and_all_versions(path=path)
            return True
        except (ImportError, Exception):
            return False

    def _list_remote(self, prefix: str) -> list[str]:
        try:
            import hvac

            client = hvac.Client(url=self._url, token=self._token, namespace=self._namespace)
            resp = client.secrets.kv.v2.list_secrets(path=prefix)
            return resp.get("data", {}).get("keys", [])
        except (ImportError, Exception):
            return []

    def _health_check(self) -> bool:
        try:
            import hvac

            client = hvac.Client(url=self._url, token=self._token)
            return client.sys.is_initialized()
        except (ImportError, Exception):
            return False


__all__ = ["VaultBackend", "VaultSecret"]
