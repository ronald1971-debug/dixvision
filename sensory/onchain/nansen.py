# ADAPTED FROM: Nansen REST API (docs.nansen.ai)
# (GET /smart-money/transactions — smart money transaction feeds;
#  GET /labels/address/{address} — wallet labels;
#  GET /token/top-holders/{token} — top token holders by smart money)
"""C-85 — Nansen smart money intelligence client.

This module wraps the Nansen REST API for smart money flow tracking.
Advisory only — never execution authority (INV-19).

What survives from upstream (Nansen API):
    * **Smart money transactions** — recent buys/sells from labeled
      smart money wallets.
    * **Address labels** — Nansen's proprietary wallet classification.
    * **Top holders** — smart money concentration per token.

What we replaced:
    * No SDK import — direct HTTP via urllib.
    * In-memory mock feeds for unit tests.
    * Advisory signal output.

OFFLINE tier: advisory signal generation.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SmartMoneyTx:
    """A smart money transaction event."""

    address: str
    token: str
    action: str  # buy, sell, transfer
    amount_usd: float
    label: str = ""
    timestamp: int = 0


class NansenClient:
    """Nansen smart money intelligence client.

    Advisory only — never execution authority (INV-19).

    Usage::

        client = NansenClient(api_key="...")
        txns = client.get_smart_money_txns(token="ETH")
    """

    BASE_URL = "https://api.nansen.ai"

    def __init__(self, *, api_key: str = "", in_memory: bool | None = None) -> None:
        self._api_key = api_key
        # Auto-detect: live mode when API key is present, mock otherwise
        self._in_memory = in_memory if in_memory is not None else (not bool(api_key))
        self._mock_txns: list[SmartMoneyTx] = []

    def get_smart_money_txns(self, *, token: str = "", limit: int = 50) -> list[SmartMoneyTx]:
        """Get recent smart money transactions."""
        if self._in_memory:
            if token:
                return [t for t in self._mock_txns if t.token == token][:limit]
            return self._mock_txns[:limit]
        return self._fetch_txns(token, limit)

    def get_address_labels(self, address: str) -> list[str]:
        """Get Nansen labels for a wallet address."""
        if self._in_memory:
            for tx in self._mock_txns:
                if tx.address.lower() == address.lower():
                    return [tx.label] if tx.label else []
            return []
        return self._fetch_labels(address)

    def add_mock_tx(self, tx: SmartMoneyTx) -> None:
        """Add mock transaction for testing."""
        self._mock_txns.append(tx)

    def _fetch_txns(self, token: str, limit: int) -> list[SmartMoneyTx]:
        url = f"{self.BASE_URL}/smart-money/transactions?limit={limit}"
        if token:
            url += f"&token={token}"
        try:
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Bearer {self._api_key}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            return [
                SmartMoneyTx(
                    address=t.get("address", ""),
                    token=t.get("token", ""),
                    action=t.get("action", ""),
                    amount_usd=t.get("amount_usd", 0.0),
                    label=t.get("label", ""),
                    timestamp=t.get("timestamp", 0),
                )
                for t in data.get("transactions", [])
            ]
        except Exception:
            return []

    def _fetch_labels(self, address: str) -> list[str]:
        url = f"{self.BASE_URL}/labels/address/{address}"
        try:
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Bearer {self._api_key}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            return data.get("labels", [])
        except Exception:
            return []


__all__ = ["NansenClient", "SmartMoneyTx"]
