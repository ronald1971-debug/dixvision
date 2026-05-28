"""Cockpit API — /operator endpoint.

Accepts and validates operator commands (halt, resume, override,
param_change). Returns action receipts. B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["OperatorCommand", "CommandReceipt", "OperatorCommandHandler"]

_VALID_ACTIONS = frozenset({"HALT", "RESUME", "OVERRIDE", "PARAM_CHANGE", "PLUGIN_TOGGLE"})


@dataclass(frozen=True, slots=True)
class OperatorCommand:
    ts_ns: int
    operator_id: str
    action: str
    target: str
    payload: dict[str, Any]
    session_id: str


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    ts_ns: int
    operator_id: str
    action: str
    target: str
    accepted: bool
    rejection_reason: str


class OperatorCommandHandler:
    """Validates and dispatches operator commands to the appropriate engine."""

    def __init__(
        self,
        halt_fn: Any,
        override_fn: Any,
        param_fn: Any,
        plugin_fn: Any,
        action_log: Any,
    ) -> None:
        self._halt = halt_fn
        self._override = override_fn
        self._param = param_fn
        self._plugin = plugin_fn
        self._log = action_log

    def handle(self, cmd: OperatorCommand) -> CommandReceipt:
        if cmd.action not in _VALID_ACTIONS:
            return CommandReceipt(
                ts_ns=cmd.ts_ns, operator_id=cmd.operator_id,
                action=cmd.action, target=cmd.target,
                accepted=False, rejection_reason=f"Unknown action: {cmd.action!r}",
            )
        try:
            if cmd.action == "HALT":
                self._halt(reason=f"operator:{cmd.operator_id}", ts_ns=cmd.ts_ns)
            elif cmd.action == "RESUME":
                self._halt.clear(ts_ns=cmd.ts_ns)
            elif cmd.action == "OVERRIDE":
                self._override(**cmd.payload, ts_ns=cmd.ts_ns)
            elif cmd.action == "PARAM_CHANGE":
                self._param(**cmd.payload, ts_ns=cmd.ts_ns)
            elif cmd.action == "PLUGIN_TOGGLE":
                self._plugin(**cmd.payload, ts_ns=cmd.ts_ns)
        except Exception as exc:  # noqa: BLE001
            return CommandReceipt(
                ts_ns=cmd.ts_ns, operator_id=cmd.operator_id,
                action=cmd.action, target=cmd.target,
                accepted=False, rejection_reason=str(exc),
            )
        from cockpit.audit.operator_actions import OperatorAction  # noqa: PLC0415
        self._log.append(OperatorAction(
            ts_ns=cmd.ts_ns, operator_id=cmd.operator_id,
            action_type=cmd.action, target=cmd.target,
            payload=cmd.payload, session_id=cmd.session_id,
        ))
        return CommandReceipt(
            ts_ns=cmd.ts_ns, operator_id=cmd.operator_id,
            action=cmd.action, target=cmd.target,
            accepted=True, rejection_reason="",
        )
