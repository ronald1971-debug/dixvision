"""Memecoin sniper (BUILD-DIRECTIVE — Tier 3).

Implements the two-phase sniping pattern from MEMECOIN_TRADING_SPEC §3:
- Phase 1: Insta-buy (block 0/1) — small position, safety-gated
- Phase 2: Confirmation add-on (30-60s later) — larger if Phase 1 clean

Sniping is OPTIONAL (gated behind memecoin_aggressive mode + operator toggle).
Default memecoin mode is NOT a sniper.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SnipePhase(StrEnum):
    """Current phase of a snipe attempt."""

    PENDING = "PENDING"
    PHASE1_EXECUTING = "PHASE1_EXECUTING"
    PHASE1_COMPLETE = "PHASE1_COMPLETE"
    PHASE2_WAITING = "PHASE2_WAITING"
    PHASE2_EXECUTING = "PHASE2_EXECUTING"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass(slots=True)
class SnipeAttempt:
    """Tracks a two-phase snipe attempt."""

    snipe_id: str
    token_address: str
    chain: str
    phase: SnipePhase
    phase1_size_sol: float
    phase2_size_sol: float
    phase1_filled: bool = False
    phase1_price: float = 0.0
    phase2_filled: bool = False
    phase2_price: float = 0.0
    safety_passed: bool = False
    confirmation_passed: bool = False
    jito_bundle_used: bool = False
    created_ts_ns: int = 0
    phase1_ts_ns: int = 0
    phase2_ts_ns: int = 0


class MemeSniper:
    """Two-phase memecoin sniper.

    Gated behind:
    - memecoin_aggressive mode
    - operator toggle enabled
    - full safety stack passed

    Never: all-in on Phase 1.
    Never: skip Phase 2 confirmation.
    """

    def __init__(
        self,
        *,
        phase1_max_sol: float = 0.2,
        phase2_multiplier: float = 3.0,
        confirmation_delay_ns: int = 30_000_000_000,  # 30 seconds
        enabled: bool = False,
    ) -> None:
        self._phase1_max = phase1_max_sol
        self._phase2_multiplier = phase2_multiplier
        self._confirmation_delay = confirmation_delay_ns
        self._enabled = enabled
        self._attempts: dict[str, SnipeAttempt] = {}

    @property
    def enabled(self) -> bool:
        """Whether sniping is active."""
        return self._enabled

    def enable(self) -> None:
        """Enable sniping (requires operator toggle)."""
        self._enabled = True

    def disable(self) -> None:
        """Disable sniping."""
        self._enabled = False

    def create_attempt(
        self,
        *,
        token_address: str,
        chain: str = "solana",
        size_sol: float | None = None,
        ts_ns: int = 0,
    ) -> SnipeAttempt | None:
        """Create a new snipe attempt (Phase 1 size capped)."""
        if not self._enabled:
            return None

        phase1_size = min(size_sol or self._phase1_max, self._phase1_max)
        phase2_size = phase1_size * self._phase2_multiplier

        snipe_id = f"snipe_{token_address[:8]}_{ts_ns}"
        attempt = SnipeAttempt(
            snipe_id=snipe_id,
            token_address=token_address,
            chain=chain,
            phase=SnipePhase.PENDING,
            phase1_size_sol=phase1_size,
            phase2_size_sol=phase2_size,
            created_ts_ns=ts_ns,
        )
        self._attempts[snipe_id] = attempt
        return attempt

    def start_phase1(self, snipe_id: str, *, safety_passed: bool, ts_ns: int = 0) -> bool:
        """Start Phase 1 execution (requires safety gate pass)."""
        attempt = self._attempts.get(snipe_id)
        if attempt is None:
            return False
        if not safety_passed:
            attempt.phase = SnipePhase.CANCELLED
            return False
        attempt.phase = SnipePhase.PHASE1_EXECUTING
        attempt.safety_passed = True
        attempt.phase1_ts_ns = ts_ns
        return True

    def complete_phase1(self, snipe_id: str, *, filled: bool, price: float = 0.0) -> None:
        """Record Phase 1 completion."""
        attempt = self._attempts.get(snipe_id)
        if attempt is None:
            return
        attempt.phase1_filled = filled
        attempt.phase1_price = price
        if filled:
            attempt.phase = SnipePhase.PHASE2_WAITING
        else:
            attempt.phase = SnipePhase.FAILED

    def can_start_phase2(self, snipe_id: str, *, ts_ns: int) -> bool:
        """Check if Phase 2 can start (delay elapsed + Phase 1 filled)."""
        attempt = self._attempts.get(snipe_id)
        if attempt is None:
            return False
        if attempt.phase != SnipePhase.PHASE2_WAITING:
            return False
        if not attempt.phase1_filled:
            return False
        elapsed = ts_ns - attempt.phase1_ts_ns
        return elapsed >= self._confirmation_delay

    def start_phase2(
        self,
        snipe_id: str,
        *,
        confirmation_passed: bool,
        ts_ns: int = 0,
    ) -> bool:
        """Start Phase 2 (requires re-run of safety + clean post-launch)."""
        attempt = self._attempts.get(snipe_id)
        if attempt is None:
            return False
        if not confirmation_passed:
            attempt.phase = SnipePhase.CANCELLED
            return False
        attempt.phase = SnipePhase.PHASE2_EXECUTING
        attempt.confirmation_passed = True
        attempt.phase2_ts_ns = ts_ns
        return True

    def complete_phase2(self, snipe_id: str, *, filled: bool, price: float = 0.0) -> None:
        """Record Phase 2 completion."""
        attempt = self._attempts.get(snipe_id)
        if attempt is None:
            return
        attempt.phase2_filled = filled
        attempt.phase2_price = price
        attempt.phase = SnipePhase.COMPLETE if filled else SnipePhase.FAILED

    @property
    def active_attempts(self) -> list[SnipeAttempt]:
        """Get all non-terminal attempts."""
        terminal = {SnipePhase.COMPLETE, SnipePhase.CANCELLED, SnipePhase.FAILED}
        return [a for a in self._attempts.values() if a.phase not in terminal]
