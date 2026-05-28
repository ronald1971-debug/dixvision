"""core.contracts.operator_authority — Operator Authority switches (BUILD-DIRECTIVE §1).

Three orthogonal switches controlled by Ronald, plus per-domain trading mode
and semi-auto policy. All frozen+slotted for immutability and INV-15 replay.

The two axes:
  AXIS 1 — Operator Authority Switches (system-wide):
    Learning:      OFF | SHADOW | FULL
    Practice:      OFF | ON
    LiveExecution: BLOCKED | ARMED

  AXIS 2 — Trading Mode (per-domain, per-execution):
    MANUAL | SEMI_AUTO | FULL_AUTO

All nine (switch × mode) combinations per domain are valid.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = (
    "LearningAuthority",
    "PracticeAuthority",
    "LiveExecutionAuthority",
    "TradingDomain",
    "TradingMode",
    "SemiAutoPolicy",
    "OperatorAuthority",
)


class LearningAuthority(StrEnum):
    """Indira/Dyon learning state."""

    OFF = "OFF"
    SHADOW = "SHADOW"
    FULL = "FULL"


class PracticeAuthority(StrEnum):
    """Paper trading / backtesting enabled."""

    OFF = "OFF"
    ON = "ON"


class LiveExecutionAuthority(StrEnum):
    """Real-money execution gate."""

    BLOCKED = "BLOCKED"
    ARMED = "ARMED"


class TradingDomain(StrEnum):
    """Hard-isolated execution domains (router.py)."""

    NORMAL = "NORMAL"
    COPY_TRADING = "COPY_TRADING"
    MEMECOIN = "MEMECOIN"


class TradingMode(StrEnum):
    """Per-domain trading mode — who pulls the trigger."""

    MANUAL = "MANUAL"
    SEMI_AUTO = "SEMI_AUTO"
    FULL_AUTO = "FULL_AUTO"


@dataclass(frozen=True, slots=True)
class SemiAutoPolicy:
    """Per-domain semi-auto policy (BUILD-DIRECTIVE §semi-auto-policy).

    When a domain is in SEMI_AUTO:
    - Entries require operator approval (configurable)
    - Exits auto-fire (Indira protects on the way out)
    - Risk reductions auto-fire
    """

    entry_requires_approval: bool = True
    exit_auto: bool = True
    risk_reduce_auto: bool = True
    notional_threshold_usd: float = 5000.0
    position_fraction_cap: float = 0.05
    volatility_cap_zscore: float = 3.0

    def __post_init__(self) -> None:
        if self.notional_threshold_usd < 0:
            msg = "notional_threshold_usd must be >= 0"
            raise ValueError(msg)
        if not (0.0 < self.position_fraction_cap <= 1.0):
            msg = "position_fraction_cap must be in (0, 1]"
            raise ValueError(msg)
        if self.volatility_cap_zscore <= 0:
            msg = "volatility_cap_zscore must be > 0"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class OperatorAuthority:
    """Immutable snapshot of all operator switches (BUILD-DIRECTIVE §1).

    The SINGLE source of truth for what is running and what is permitted.
    Mutated ONLY by ``OperatorInterfaceBridge`` (B-OPAUTH lint rule).
    """

    learning: LearningAuthority = LearningAuthority.FULL
    practice: PracticeAuthority = PracticeAuthority.ON
    live_execution: LiveExecutionAuthority = LiveExecutionAuthority.BLOCKED
    trading_mode: Mapping[TradingDomain, TradingMode] = None  # type: ignore[assignment]
    semi_auto_policy: Mapping[TradingDomain, SemiAutoPolicy] = None  # type: ignore[assignment]
    operator_id: str = "ronald"
    granted_ts_ns: int = 0
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.operator_id:
            msg = "operator_id must be non-empty"
            raise ValueError(msg)
        if self.granted_ts_ns < 0:
            msg = "granted_ts_ns must be >= 0"
            raise ValueError(msg)
        # Default trading_mode if None
        if self.trading_mode is None:
            object.__setattr__(
                self,
                "trading_mode",
                {
                    TradingDomain.NORMAL: TradingMode.FULL_AUTO,
                    TradingDomain.COPY_TRADING: TradingMode.SEMI_AUTO,
                    TradingDomain.MEMECOIN: TradingMode.MANUAL,
                },
            )
        # Default semi_auto_policy if None
        if self.semi_auto_policy is None:
            object.__setattr__(
                self,
                "semi_auto_policy",
                {
                    TradingDomain.NORMAL: SemiAutoPolicy(),
                    TradingDomain.COPY_TRADING: SemiAutoPolicy(
                        notional_threshold_usd=2000.0,
                        position_fraction_cap=0.02,
                        volatility_cap_zscore=2.5,
                    ),
                    TradingDomain.MEMECOIN: SemiAutoPolicy(
                        notional_threshold_usd=500.0,
                        position_fraction_cap=0.01,
                        volatility_cap_zscore=4.0,
                    ),
                },
            )
        # Validate all domains have mode + policy
        for domain in TradingDomain:
            if domain not in self.trading_mode:
                msg = f"trading_mode missing for domain {domain}"
                raise ValueError(msg)
            if domain not in self.semi_auto_policy:
                msg = f"semi_auto_policy missing for domain {domain}"
                raise ValueError(msg)
