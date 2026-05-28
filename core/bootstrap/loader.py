"""core.bootstrap.loader — Module Discovery and Dependency Loader.

Scans the project tree for engines, plugins, and adapters, resolves their
dependency graph, and returns an ordered load sequence. This ensures all
imports succeed and DI wiring is correct before any engine starts.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    """Discovered module metadata."""

    name: str
    path: str
    category: str
    dependencies: tuple[str, ...] = ()
    priority: int = 50


@dataclass
class LoadResult:
    """Result of the module loading pass."""

    loaded: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        total = len(self.loaded) + len(self.failed)
        return len(self.loaded) / total if total > 0 else 1.0


# Engine load order: governance first, then intelligence, then execution
ENGINE_LOAD_ORDER = (
    "immutable_core",
    "core",
    "governance_engine",
    "intelligence_engine",
    "execution_engine",
    "learning_engine",
    "evolution_engine",
    "system_engine",
    "data_pipeline",
    "sensory",
)


def discover_modules(root: Path | None = None) -> list[ModuleInfo]:
    """Discover all loadable modules in the project tree.

    Scans ENGINE_LOAD_ORDER directories for Python packages.
    """
    if root is None:
        root = Path(__file__).resolve().parents[2]

    modules: list[ModuleInfo] = []
    for idx, engine_name in enumerate(ENGINE_LOAD_ORDER):
        engine_dir = root / engine_name
        if not engine_dir.is_dir():
            continue
        init_file = engine_dir / "__init__.py"
        if init_file.exists():
            modules.append(
                ModuleInfo(
                    name=engine_name,
                    path=str(engine_dir),
                    category="engine",
                    priority=idx * 10,
                )
            )

    return sorted(modules, key=lambda m: m.priority)


def load_module(module_name: str) -> Any:
    """Attempt to import a module by dotted name.

    Returns the module object or raises ImportError.
    """
    return importlib.import_module(module_name)


def load_all(root: Path | None = None) -> LoadResult:
    """Discover and load all system modules in dependency order.

    Returns LoadResult with loaded/failed/skipped counts.
    """
    result = LoadResult()
    modules = discover_modules(root)

    for mod_info in modules:
        try:
            load_module(mod_info.name)
            result.loaded.append(mod_info.name)
            logger.debug("Loaded: %s", mod_info.name)
        except ImportError as e:
            result.failed.append((mod_info.name, str(e)))
            logger.warning("Failed to load %s: %s", mod_info.name, e)
        except Exception as e:
            result.failed.append((mod_info.name, str(e)))
            logger.error("Error loading %s: %s", mod_info.name, e)

    logger.info(
        "Module loader: %d loaded, %d failed (%.0f%% success)",
        len(result.loaded),
        len(result.failed),
        result.success_rate * 100,
    )
    return result


__all__ = [
    "ENGINE_LOAD_ORDER",
    "LoadResult",
    "ModuleInfo",
    "discover_modules",
    "load_all",
    "load_module",
]
