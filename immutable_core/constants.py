"""immutable_core.constants — System Invariants (LEAN4 Verified Floors).

Non-negotiable safety invariants verified by formal proofs in
``immutable_core/safety_axioms.lean``. These constants define the absolute
floors that NO runtime code may breach. The kill switch fires unconditionally
on any violation.

These are FROZEN. They cannot be changed at runtime. They cannot be changed
by operator authority. They can only be updated via a formal amendment process
through the sandbox pipeline (single operator approval since Ronald is sole
authority).

References:
- INV-15: Replay determinism
- INV-19/71: Authority symmetry
- INV-49: Hysteresis
- INV-52: Shadow policy
- INV-56: Triad lock (Decider/Executor/Approver isolation)
- INV-68: ExecutionIntent immutability
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class SafetyTier(IntEnum):
    """Safety tier classification for invariant violations."""

    ADVISORY = 0
    DEGRADED = 1
    HALT = 2
    KILL = 3


@dataclass(frozen=True)
class SafetyAxioms:
    """LEAN4-verified safety floors. Immutable at runtime.

    Any breach triggers immediate kill switch activation via
    ``immutable_core/kill_switch.py``. No exception. No override.
    """

    # Absolute drawdown floor — system halts if breached
    MAX_DRAWDOWN_FLOOR_PCT: float = 4.0

    # Maximum loss per individual trade
    MAX_LOSS_PER_TRADE_FLOOR_PCT: float = 1.0

    # Fail-closed: if governance cannot verify, deny execution
    FAIL_CLOSED: bool = True

    # Credentials never leave the local machine
    CREDENTIALS_LOCAL_ONLY: bool = True

    # Hot-path maximum allowed latency before degraded mode
    FAST_PATH_MAX_LATENCY_MS: float = 5.0

    # Maximum exposure per-domain as fraction of total equity
    MAX_DOMAIN_EXPOSURE_PCT: float = 30.0

    # Maximum total exposure across all domains
    MAX_TOTAL_EXPOSURE_PCT: float = 80.0

    # Minimum time between consecutive live orders (prevents runaway)
    MIN_ORDER_INTERVAL_MS: float = 100.0

    # Maximum position count per domain
    MAX_POSITIONS_PER_DOMAIN: int = 50

    # Maximum consecutive losses before auto-degradation
    MAX_CONSECUTIVE_LOSSES: int = 5

    # Hash chain integrity — every Nth event gets a full verification
    INTEGRITY_CHECK_INTERVAL: int = 100

    # Kill switch activation cooldown (cannot be re-armed within this period)
    KILL_SWITCH_COOLDOWN_MS: float = 60_000.0

    # Maximum replay divergence tolerance (bits)
    REPLAY_DIVERGENCE_TOLERANCE_BITS: int = 0


@dataclass(frozen=True)
class InvariantRegistry:
    """Registry of all system invariants with their enforcement tiers.

    Each invariant maps to a SafetyTier that determines the response on breach:
    - ADVISORY: log + metric
    - DEGRADED: auto-downgrade SystemMode
    - HALT: emergency halt via StateTransitionManager
    - KILL: immediate kill switch (bypass all FSM)
    """

    INV_15_REPLAY_DETERMINISM: SafetyTier = SafetyTier.KILL
    INV_19_AUTHORITY_SYMMETRY: SafetyTier = SafetyTier.HALT
    INV_49_HYSTERESIS: SafetyTier = SafetyTier.DEGRADED
    INV_52_SHADOW_POLICY: SafetyTier = SafetyTier.DEGRADED
    INV_56_TRIAD_LOCK: SafetyTier = SafetyTier.KILL
    INV_68_EXECUTION_INTENT_IMMUTABILITY: SafetyTier = SafetyTier.KILL
    INV_71_HAZARD_AUTHORITY: SafetyTier = SafetyTier.HALT
    B25_GOVERNANCE_BYPASS: SafetyTier = SafetyTier.KILL
    B27_HAZARD_CONSTRUCTION: SafetyTier = SafetyTier.HALT
    B30_EXTERNAL_ADAPTER_READ_ONLY: SafetyTier = SafetyTier.HALT
    B33_RAW_CLOCK_BAN: SafetyTier = SafetyTier.ADVISORY
    B34_MANUAL_INTENT_PRODUCER: SafetyTier = SafetyTier.HALT


# Singleton — immutable, globally available
AXIOMS = SafetyAxioms()
INVARIANTS = InvariantRegistry()

# System identity constants
SYSTEM_NAME = "DIX VISION"
SYSTEM_VERSION = "v42.2"
SYSTEM_CODENAME = "INDIRA"
LEDGER_SCHEMA_VERSION = 3
HASH_ALGORITHM = "blake2b"
SIGNATURE_ALGORITHM = "hmac-sha256"


__all__ = [
    "AXIOMS",
    "HASH_ALGORITHM",
    "INVARIANTS",
    "InvariantRegistry",
    "LEDGER_SCHEMA_VERSION",
    "SIGNATURE_ALGORITHM",
    "SYSTEM_CODENAME",
    "SYSTEM_NAME",
    "SYSTEM_VERSION",
    "SafetyAxioms",
    "SafetyTier",
]
