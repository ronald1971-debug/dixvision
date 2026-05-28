# ADAPTED FROM: Arkham Intelligence REST API (docs.arkhamintelligence.com)
# (GET /api/v1/intel/address/{address} — wallet entity identification;
#  GET /api/v1/transactions/ — transaction history;
#  entity_type: exchange, whale, dex_lp, fund, dao)
"""C-83 — Arkham Intelligence wallet entity labeling client.

This module wraps the Arkham Intelligence REST API for identifying
known exchange wallets, whale wallets, and DEX LPs. Advisory only (INV-19).

What survives from upstream (Arkham API):
    * **Address intel** — ``/api/v1/intel/address/{addr}``: returns
      entity_type, entity_label, tags for a wallet address.
    * **Transactions** — ``/api/v1/transactions/``: recent transactions
      for an address.

What we replaced:
    * No SDK import — direct HTTP via urllib.
    * In-memory mock wallet labels for unit tests.
    * Output advisory SignalEvent with entity info.

OFFLINE tier: advisory signal generation.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WalletEntity:
    """Entity label for a blockchain address."""

    address: str
    entity_type: str  # exchange, whale, dex_lp, fund, dao, unknown
    entity_label: str
    tags: tuple[str, ...] = ()
    confidence: float = 0.0


class ArkhamClient:
    """Arkham Intelligence wallet entity labeling client.

    Advisory only — never execution authority (INV-19).

    Usage::

        client = ArkhamClient(api_key="...")
        entity = client.get_entity("0x1234...")
    """

    BASE_URL = "https://api.arkhamintelligence.com"

    def __init__(self, *, api_key: str = "", in_memory: bool | None = None) -> None:
        self._api_key = api_key
        # Auto-detect: live mode when API key is present, mock otherwise
        self._in_memory = in_memory if in_memory is not None else (not bool(api_key))
        self._mock_entities: dict[str, WalletEntity] = {}

    def get_entity(self, address: str) -> WalletEntity | None:
        """Get entity label for a wallet address."""
        if self._in_memory:
            return self._mock_entities.get(address.lower())
        return self._fetch_entity(address)

    def add_mock_entity(self, entity: WalletEntity) -> None:
        """Add mock entity for testing."""
        self._mock_entities[entity.address.lower()] = entity

    def _fetch_entity(self, address: str) -> WalletEntity | None:
        url = f"{self.BASE_URL}/api/v1/intel/address/{address}"
        try:
            req = urllib.request.Request(url)
            req.add_header("API-Key", self._api_key)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            return WalletEntity(
                address=address,
                entity_type=data.get("entity_type", "unknown"),
                entity_label=data.get("entity_label", ""),
                tags=tuple(data.get("tags", [])),
                confidence=data.get("confidence", 0.0),
            )
        except Exception:
            return None


__all__ = ["ArkhamClient", "WalletEntity"]
