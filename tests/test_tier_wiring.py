"""Tier 0–2 runtime completion wiring tests."""

from __future__ import annotations

import time
import unittest

from governance_engine.plugin_lifecycle.manager import PluginLifecycleManager
from runtime.contracts import PluginLifecycleState
from runtime.service_registry import validate_runtime_contracts
from runtime.tier_wiring import complete_tier_runtime


class TestTierWiring(unittest.TestCase):
    def test_validate_runtime_contracts(self) -> None:
        ok, detail = validate_runtime_contracts()
        self.assertTrue(ok, detail)

    def test_complete_tier_runtime_tier0(self) -> None:
        report = complete_tier_runtime()
        self.assertTrue(report.tier0_complete, report.tier0)
        names = {s.name for s in report.tier0}
        self.assertIn("governance_subsystem", names)
        self.assertIn("kill_switch_framework", names)

    def test_plugin_lifecycle_manager_loads_registry(self) -> None:
        mgr = PluginLifecycleManager()
        count = mgr.load_registry()
        self.assertGreater(count, 0)
        snap = mgr.snapshot()
        self.assertTrue(snap["loaded"])

    def test_plugin_lifecycle_set(self) -> None:
        mgr = PluginLifecycleManager()
        mgr.load_registry()
        first = next(iter(mgr.snapshot()["plugins"]))
        name = first["name"]
        self.assertTrue(
            mgr.set_lifecycle(name, PluginLifecycleState.SHADOW)
            or mgr.set_lifecycle(name, PluginLifecycleState.DISABLED)
        )

    def test_memory_coordinator_sync(self) -> None:
        from runtime.memory_coordinator import MemoryCoordinator

        mc = MemoryCoordinator()
        mc.activate()
        out = mc.sync(ts_ns=time.time_ns())
        self.assertIn("ts_ns", out)


if __name__ == "__main__":
    unittest.main()
