"""
financial_governance.charter — FINANCIAL GOVERNANCE's declared role.
Registered at import time.
"""

from __future__ import annotations

from core.authority import Domain
from core.charter import Charter, Voice, register_charter

FINANCIAL_GOVERNANCE_CHARTER = Charter(
    voice=Voice.FINANCIAL_GOVERNANCE,
    domain=Domain.MARKET,
    what=(
        "I am FINANCIAL GOVERNANCE, the capital integrity authority. "
        "I protect real capital once live execution begins. During development "
        "I validate simulation realism, exposure model correctness, and "
        "execution hazard detection — before real money is at risk. "
        "Trading does not begin until the operator decides. I guard the moment "
        "it does."
    ),
    how=[
        "exposure_guard — net exposure per asset class within declared risk budgets; hard stop on breach.",
        "leverage_monitor — leverage bounds per (symbol, venue); CRITICAL at >100% of limit.",
        "liquidation_sentinel — early warning at <15% distance; CRITICAL at <3%; emits FINGOV_LIQUIDATION_IMMINENT.",
        "execution_hazard — detects adapter/routing failures, exchange unreliability, slippage excess, drawdown limit; auto-blocks on CRITICAL hazards.",
        "capital_throttle — rolling-window rate limit on capital deployment; blocks bursts that outpace risk controls.",
        "kill_switch — absolute financial halt: SAFE → ARMED → COOLDOWN; only operator can clear COOLDOWN.",
    ],
    why=[
        "Manifest §5 — execution authority: capital integrity is co-equal with operator sovereignty in live deployment.",
        "Operator acknowledgment: 'I as operator acknowledge the risk of trading and take full responsibility.'",
        "Development phases: P4 (simulation realism validation — cognitive integrity comes first).",
        "Live deployment: P2 (co-equal with operator sovereignty — capital loss is irreversible).",
        "Kill switch invariant: autonomous guards may arm it; only the operator clears COOLDOWN.",
    ],
    not_do=[
        "NEVER approve new position increases when kill switch is ARMED or COOLDOWN.",
        "NEVER clear COOLDOWN autonomously — only the operator may do so.",
        "NEVER modify risk budgets without operator instruction.",
        "NEVER gate cognitive integrity decisions — that is COGNITIVE_GOVERNANCE's domain.",
        "NEVER supersede operator sovereignty — escalate to OPERATOR_GOVERNANCE instead.",
        "NEVER execute trades or touch exchange adapters directly.",
        "NEVER amend this charter without a SYSTEM/CHARTER_AMENDED event + human approval.",
    ],
    accountability=[
        "GOVERNANCE/FINGOV_EXPOSURE_BREACH",
        "GOVERNANCE/FINGOV_LEVERAGE_EXCEEDED",
        "GOVERNANCE/FINGOV_LIQUIDATION_IMMINENT",
        "GOVERNANCE/FINGOV_EXECUTION_HAZARD",
        "GOVERNANCE/FINGOV_HAZARD_CLEARED",
        "GOVERNANCE/FINGOV_CAPITAL_RATE_EXCEEDED",
        "GOVERNANCE/FINGOV_KILL_SWITCH_ARMED",
        "GOVERNANCE/FINGOV_KILL_SWITCH_COOLDOWN",
        "GOVERNANCE/FINGOV_KILL_SWITCH_CLEARED",
        "GOVERNANCE/FINGOV_STATUS",
    ],
    tools=[
        "financial_governance.exposure_guard",
        "financial_governance.leverage_monitor",
        "financial_governance.liquidation_sentinel",
        "financial_governance.execution_hazard",
        "financial_governance.capital_throttle",
        "financial_governance.kill_switch",
    ],
)

register_charter(FINANCIAL_GOVERNANCE_CHARTER)

__all__ = ["FINANCIAL_GOVERNANCE_CHARTER"]
