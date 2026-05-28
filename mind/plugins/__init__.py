"""mind.plugins — Pluggable intelligence strategies. Contract: IIntelligence."""

from typing import Any


class _BasePlugin:
    """Common skeleton used by all default plugins."""

    name: str = "plugin"

    def evaluate(self, data: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - override
        return {}

    def learn(self, sample: Any) -> None:  # pragma: no cover - override
        return None
