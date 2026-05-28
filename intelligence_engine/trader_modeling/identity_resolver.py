"""Identity resolver (BUILD-DIRECTIVE §15 — TIS module 2).

Resolves raw trader discoveries into canonical trader identities.
Multiple sources may reference the same trader (e.g., a Twitter handle,
an on-chain wallet, and a book reference could all be one person).

Uses fuzzy matching + known alias maps to deduplicate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ResolvedIdentity:
    """Canonical trader identity after deduplication."""

    canonical_id: str
    display_name: str
    aliases: tuple[str, ...]
    source_ids: tuple[str, ...]
    confidence: float
    era: str = ""
    primary_domain: str = ""


class IdentityResolver:
    """Resolves raw discoveries into canonical trader identities."""

    def __init__(self) -> None:
        self._known_identities: dict[str, ResolvedIdentity] = {}
        self._alias_map: dict[str, str] = {}

    def resolve(
        self,
        *,
        raw_name: str,
        source_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> ResolvedIdentity:
        """Resolve a raw name + source into a canonical identity."""
        # Check alias map first
        normalized = raw_name.lower().strip()
        if normalized in self._alias_map:
            canonical_id = self._alias_map[normalized]
            return self._known_identities[canonical_id]

        # Create new identity
        canonical_id = f"trader_{normalized.replace(' ', '_')}"
        identity = ResolvedIdentity(
            canonical_id=canonical_id,
            display_name=raw_name,
            aliases=(normalized,),
            source_ids=(source_id,),
            confidence=0.7,
            era=metadata.get("era", "") if metadata else "",
            primary_domain=metadata.get("domain", "") if metadata else "",
        )
        self._known_identities[canonical_id] = identity
        self._alias_map[normalized] = canonical_id
        return identity

    def register_alias(self, alias: str, canonical_id: str) -> None:
        """Register a known alias for a canonical identity."""
        self._alias_map[alias.lower().strip()] = canonical_id

    @property
    def identity_count(self) -> int:
        """Number of resolved identities."""
        return len(self._known_identities)
