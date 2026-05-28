"""Semi-auto auto-exit handler (BUILD-DIRECTIVE §8).

In SEMI_AUTO mode, exits and risk-reductions auto-fire without waiting for
operator approval. Indira produces the exit signal; this handler ensures
it executes immediately regardless of threshold settings.

This module is also responsible for stop-loss and trailing-stop exits that
fire automatically to protect capital.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExitReason(StrEnum):
    """Why an auto-exit fired."""

    SIGNAL_EXIT = "SIGNAL_EXIT"
    STOP_LOSS = "STOP_LOSS"
    TRAILING_STOP = "TRAILING_STOP"
    RISK_REDUCE = "RISK_REDUCE"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True, slots=True)
class AutoExitDecision:
    """Immutable record of an auto-exit decision."""

    domain: str
    symbol: str
    reason: ExitReason
    ts_ns: int
    pnl_estimate_usd: float = 0.0
    notes: str = ""


def should_auto_exit(
    *,
    is_exit: bool,
    is_risk_reduce: bool,
    has_stop_loss_trigger: bool,
    has_trailing_stop_trigger: bool,
    drawdown_fraction: float,
    max_drawdown_cap: float,
) -> ExitReason | None:
    """Determine if an auto-exit should fire.

    Returns the ExitReason if exit should fire, None otherwise.
    """
    if is_exit:
        return ExitReason.SIGNAL_EXIT
    if is_risk_reduce:
        return ExitReason.RISK_REDUCE
    if has_stop_loss_trigger:
        return ExitReason.STOP_LOSS
    if has_trailing_stop_trigger:
        return ExitReason.TRAILING_STOP
    if drawdown_fraction >= max_drawdown_cap:
        return ExitReason.MAX_DRAWDOWN
    return None
