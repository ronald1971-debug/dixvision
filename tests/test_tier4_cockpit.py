"""Tests for Tier 4.2 — Cockpit Operator IDE."""

from cockpit.operator_ide import (
    IDELayout,
    IDEPanel,
    OperatorIDE,
)


def test_ide_default_layout():
    ide = OperatorIDE()
    assert len(ide.layout.panels) == 4
    assert IDEPanel.PERFORMANCE in ide.layout.panels


def test_ide_command_search():
    ide = OperatorIDE()
    results = ide.search_commands("pause")
    assert len(results) >= 1
    assert results[0].label == "Pause All Trading"


def test_ide_command_search_by_category():
    ide = OperatorIDE()
    results = ide.search_commands("governance")
    assert any(c.category == "governance" for c in results)


def test_ide_signal_buffer():
    ide = OperatorIDE()
    for i in range(10):
        ide.ingest_signal({"id": i, "type": "sentiment", "value": 0.5})

    signals = ide.get_recent_signals(limit=5)
    assert len(signals) == 5
    assert signals[-1]["id"] == 9


def test_ide_system_health():
    ide = OperatorIDE()
    health = ide.get_system_health()
    assert health.engines["intelligence"] == "healthy"
    assert health.engines["governance"] == "healthy"


def test_ide_custom_layout():
    layout = IDELayout(
        panels=(IDEPanel.STRATEGY_EDITOR, IDEPanel.REPLAY_VIEWER),
        density="compact",
        columns=1,
    )
    ide = OperatorIDE(layout=layout)
    assert len(ide.layout.panels) == 2
    assert ide.layout.density == "compact"
