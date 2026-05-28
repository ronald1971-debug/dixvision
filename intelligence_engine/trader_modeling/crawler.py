"""Trader crawler (BUILD-DIRECTIVE §15 — TIS module 1).

Discovers and fetches raw trader data from configured sources:
- On-chain wallets (high-P&L Solana/ETH addresses)
- Platform profiles (Twitter/X bios, TradingView profiles)
- Book/podcast references (Market Wizards, etc.)

The crawler outputs raw observations for the identity_resolver
and content_parser downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class TraderSourceType(StrEnum):
    """Type of source where trader data was discovered."""

    ONCHAIN = "ONCHAIN"
    SOCIAL = "SOCIAL"
    BOOK = "BOOK"
    PODCAST = "PODCAST"
    INTERVIEW = "INTERVIEW"
    PLATFORM = "PLATFORM"


@dataclass(frozen=True, slots=True)
class RawTraderDiscovery:
    """Raw discovery from the crawler — unresolved identity."""

    source_type: TraderSourceType
    source_id: str
    raw_name: str
    raw_data: dict[str, Any]
    ts_ns: int
    confidence: float = 0.0


class TraderCrawler:
    """Discovers traders from configured sources."""

    def fetch_onchain_discoveries(
        self, *, wallet_data: list[dict[str, Any]]
    ) -> list[RawTraderDiscovery]:
        """Fetch high-P&L wallet discoveries."""
        return [
            RawTraderDiscovery(
                source_type=TraderSourceType.ONCHAIN,
                source_id=str(w.get("address", "")),
                raw_name=str(w.get("label", "")),
                raw_data=w,
                ts_ns=int(w.get("ts_ns", 0)),
                confidence=float(w.get("pnl_confidence", 0.0)),
            )
            for w in wallet_data
        ]

    def fetch_book_references(
        self, *, references: list[dict[str, Any]]
    ) -> list[RawTraderDiscovery]:
        """Fetch trader references from books/podcasts."""
        return [
            RawTraderDiscovery(
                source_type=TraderSourceType.BOOK,
                source_id=str(r.get("book", "")),
                raw_name=str(r.get("trader_name", "")),
                raw_data=r,
                ts_ns=int(r.get("ts_ns", 0)),
                confidence=0.9,
            )
            for r in references
        ]
