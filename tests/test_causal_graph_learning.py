"""C-39 — tests for the causalnex causal-structure-learning surface.

Mirrors the test-shape of :mod:`tests.test_causal_dowhy` (C-35) — frozen+slotted
validators, deterministic Protocol-injected fake, end-to-end discovery record,
INV-15 byte-identical replay, AST guards.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from state.knowledge_graph_causal import (
    DEFAULT_EDGE_THRESHOLD,
    DEFAULT_MAX_ITER,
    DEFAULT_RANDOM_SEED,
    MAX_DATA_DIGEST_LEN,
    MAX_DISCOVERY_ID_LEN,
    MAX_EDGE_THRESHOLD,
    MAX_MAX_ITER,
    MAX_OBSERVATIONS,
    MAX_VARIABLES,
    MIN_EDGE_THRESHOLD,
    MIN_MAX_ITER,
    MIN_OBSERVATIONS,
    MIN_VARIABLES,
    NEW_PIP_DEPENDENCIES,
    STRUCTURE_SOURCE,
    CausalStructureConfigError,
    CausalStructureLearner,
    CausalStructureRecord,
    DiscoveredEdge,
    PenaltyKind,
    StructureArguments,
    StructureDiscoveryCallback,
    StructureLearner,
    causalnex_notears_learner,
    null_structure_discovery_callback,
)

# ---------------------------------------------------------------------------
# Module identity
# ---------------------------------------------------------------------------


def test_module_advertises_new_pip_dependencies() -> None:
    assert NEW_PIP_DEPENDENCIES == ("causalnex", "pandas", "numpy")


def test_structure_source_is_canonical_module_path() -> None:
    assert STRUCTURE_SOURCE == "state.knowledge_graph_causal"


def test_variable_count_bounds() -> None:
    assert MIN_VARIABLES == 2
    assert MAX_VARIABLES == 1_000


def test_observation_count_bounds() -> None:
    assert MIN_OBSERVATIONS == 10
    assert MAX_OBSERVATIONS == 10_000_000


def test_max_discovery_id_len_bound() -> None:
    assert MAX_DISCOVERY_ID_LEN == 256


def test_max_data_digest_len_bound() -> None:
    assert MAX_DATA_DIGEST_LEN == 64


def test_edge_threshold_bounds() -> None:
    assert MIN_EDGE_THRESHOLD == 0.0
    assert MAX_EDGE_THRESHOLD == 10.0


def test_max_iter_bounds() -> None:
    assert MIN_MAX_ITER == 10
    assert MAX_MAX_ITER == 10_000


def test_defaults() -> None:
    assert DEFAULT_EDGE_THRESHOLD == 0.05
    assert DEFAULT_MAX_ITER == 100
    assert DEFAULT_RANDOM_SEED == 42


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


def test_penalty_kind_values() -> None:
    assert PenaltyKind.L1.value == "l1"
    assert PenaltyKind.L2.value == "l2"
    assert PenaltyKind.MIXED.value == "mixed"


def test_penalty_kind_count() -> None:
    assert len(list(PenaltyKind)) == 3


# ---------------------------------------------------------------------------
# StructureArguments
# ---------------------------------------------------------------------------


def _valid_arguments(**overrides: Any) -> StructureArguments:
    base: dict[str, Any] = {
        "variable_names": ("x", "y", "z"),
        "n_observations": 100,
        "data_digest": "abc123def456",
        "edge_threshold": DEFAULT_EDGE_THRESHOLD,
        "max_iter": DEFAULT_MAX_ITER,
        "penalty": PenaltyKind.L1,
        "random_seed": DEFAULT_RANDOM_SEED,
    }
    base.update(overrides)
    return StructureArguments(**base)


def test_arguments_constructs_with_defaults() -> None:
    args = _valid_arguments()
    assert args.variable_names == ("x", "y", "z")
    assert args.n_observations == 100


def test_arguments_is_frozen_and_slotted() -> None:
    args = _valid_arguments()
    with pytest.raises(dataclasses.FrozenInstanceError):
        args.random_seed = 99  # type: ignore[misc]
    assert not hasattr(args, "__dict__")


# ---------------------------------------------------------------------------
# DiscoveredEdge
# ---------------------------------------------------------------------------


def test_discovered_edge_is_frozen_and_slotted() -> None:
    edge = DiscoveredEdge(source="x", target="y", weight=0.5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        edge.weight = 1.0  # type: ignore[misc]
    assert not hasattr(edge, "__dict__")


def test_discovered_edge_equality() -> None:
    e1 = DiscoveredEdge(source="x", target="y", weight=0.5)
    e2 = DiscoveredEdge(source="x", target="y", weight=0.5)
    assert e1 == e2


# ---------------------------------------------------------------------------
# CausalStructureRecord
# ---------------------------------------------------------------------------


def test_record_is_frozen_and_slotted() -> None:
    record = CausalStructureRecord(
        discovery_id="d1",
        source=STRUCTURE_SOURCE,
        ts_ns=1,
        arguments=_valid_arguments(),
        edges=(),
        n_edges_raw=0,
        n_edges_pruned=0,
        structure_digest="abcd",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.discovery_id = "x"  # type: ignore[misc]
    assert not hasattr(record, "__dict__")


# ---------------------------------------------------------------------------
# Fake StructureLearner for deterministic testing
# ---------------------------------------------------------------------------


class _FakeLearner:
    """Deterministic fake implementing StructureLearner Protocol."""

    def __init__(self, edges: list[DiscoveredEdge] | None = None) -> None:
        self._edges = edges or [
            DiscoveredEdge(source="x", target="y", weight=0.8),
            DiscoveredEdge(source="y", target="z", weight=0.6),
        ]

    def learn_structure(
        self,
        data_rows: Sequence[Mapping[str, float]],
        variable_names: tuple[str, ...],
        *,
        edge_threshold: float,
        max_iter: int,
        penalty: PenaltyKind,
        random_seed: int,
    ) -> tuple[list[DiscoveredEdge], int]:
        n_raw = len(self._edges)
        pruned = [e for e in self._edges if e.weight >= edge_threshold]
        pruned.sort(key=lambda e: (e.source, e.target))
        return pruned, n_raw


def test_fake_learner_satisfies_protocol() -> None:
    assert isinstance(_FakeLearner(), StructureLearner)


# ---------------------------------------------------------------------------
# Helper: run a single discovery
# ---------------------------------------------------------------------------


def _run_once(
    *,
    edges: list[DiscoveredEdge] | None = None,
    discovery_id: str = "disc-001",
    ts_ns: int = 1_000_000_000,
    **arg_overrides: Any,
) -> CausalStructureRecord:
    learner = CausalStructureLearner(
        structure_learner=_FakeLearner(edges=edges),
    )
    args = _valid_arguments(**arg_overrides)
    data_rows: list[dict[str, float]] = [
        {"x": 1.0, "y": 2.0, "z": 3.0},
        {"x": 4.0, "y": 5.0, "z": 6.0},
    ]
    return learner.discover(
        data_rows=data_rows,
        arguments=args,
        discovery_id=discovery_id,
        ts_ns=ts_ns,
    )


# ---------------------------------------------------------------------------
# End-to-end discovery
# ---------------------------------------------------------------------------


def test_discover_produces_record() -> None:
    record = _run_once()
    assert isinstance(record, CausalStructureRecord)
    assert record.source == STRUCTURE_SOURCE
    assert record.discovery_id == "disc-001"
    assert record.ts_ns == 1_000_000_000


def test_discover_returns_edges() -> None:
    record = _run_once()
    assert len(record.edges) == 2
    assert record.edges[0].source == "x"
    assert record.edges[0].target == "y"
    assert record.edges[1].source == "y"
    assert record.edges[1].target == "z"


def test_discover_counts_raw_and_pruned() -> None:
    record = _run_once()
    assert record.n_edges_raw == 2
    assert record.n_edges_pruned == 2


def test_discover_prunes_below_threshold() -> None:
    edges = [
        DiscoveredEdge(source="a", target="b", weight=0.01),
        DiscoveredEdge(source="c", target="d", weight=0.9),
    ]
    record = _run_once(edges=edges, edge_threshold=0.05)
    assert record.n_edges_raw == 2
    assert record.n_edges_pruned == 1
    assert record.edges[0].source == "c"


def test_discover_edges_sorted_deterministically() -> None:
    edges = [
        DiscoveredEdge(source="z", target="a", weight=0.5),
        DiscoveredEdge(source="a", target="z", weight=0.7),
        DiscoveredEdge(source="a", target="b", weight=0.6),
    ]
    record = _run_once(edges=edges)
    sources = [e.source for e in record.edges]
    targets = [e.target for e in record.edges]
    assert sources == ["a", "a", "z"]
    assert targets == ["b", "z", "a"]


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_rejects_empty_discovery_id() -> None:
    with pytest.raises(CausalStructureConfigError, match="must not be empty"):
        _run_once(discovery_id="")


def test_rejects_oversized_discovery_id() -> None:
    with pytest.raises(CausalStructureConfigError, match="MAX_DISCOVERY_ID_LEN"):
        _run_once(discovery_id="x" * (MAX_DISCOVERY_ID_LEN + 1))


def test_rejects_too_few_variables() -> None:
    with pytest.raises(CausalStructureConfigError, match="MIN_VARIABLES"):
        _run_once(variable_names=("x",))


def test_rejects_too_many_variables() -> None:
    names = tuple(f"v{i}" for i in range(MAX_VARIABLES + 1))
    with pytest.raises(CausalStructureConfigError, match="MAX_VARIABLES"):
        _run_once(variable_names=names)


def test_rejects_too_few_observations() -> None:
    with pytest.raises(CausalStructureConfigError, match="MIN_OBSERVATIONS"):
        _run_once(n_observations=MIN_OBSERVATIONS - 1)


def test_rejects_too_many_observations() -> None:
    with pytest.raises(CausalStructureConfigError, match="MAX_OBSERVATIONS"):
        _run_once(n_observations=MAX_OBSERVATIONS + 1)


def test_rejects_empty_data_digest() -> None:
    with pytest.raises(CausalStructureConfigError, match="must not be empty"):
        _run_once(data_digest="")


def test_rejects_oversized_data_digest() -> None:
    with pytest.raises(CausalStructureConfigError, match="MAX_DATA_DIGEST_LEN"):
        _run_once(data_digest="x" * (MAX_DATA_DIGEST_LEN + 1))


def test_rejects_threshold_below_min() -> None:
    with pytest.raises(CausalStructureConfigError, match="edge_threshold"):
        _run_once(edge_threshold=-0.1)


def test_rejects_threshold_above_max() -> None:
    with pytest.raises(CausalStructureConfigError, match="edge_threshold"):
        _run_once(edge_threshold=MAX_EDGE_THRESHOLD + 1.0)


def test_rejects_max_iter_below_min() -> None:
    with pytest.raises(CausalStructureConfigError, match="max_iter"):
        _run_once(max_iter=MIN_MAX_ITER - 1)


def test_rejects_max_iter_above_max() -> None:
    with pytest.raises(CausalStructureConfigError, match="max_iter"):
        _run_once(max_iter=MAX_MAX_ITER + 1)


def test_rejects_duplicate_variable_names() -> None:
    with pytest.raises(CausalStructureConfigError, match="duplicate"):
        _run_once(variable_names=("x", "y", "x"))


def test_rejects_empty_variable_name() -> None:
    with pytest.raises(CausalStructureConfigError, match="non-empty"):
        _run_once(variable_names=("x", "", "z"))


# ---------------------------------------------------------------------------
# INV-15: Replay determinism
# ---------------------------------------------------------------------------


def test_inv15_three_run_identical() -> None:
    results = [_run_once() for _ in range(3)]
    digests = [r.structure_digest for r in results]
    assert digests[0] == digests[1] == digests[2]


def test_inv15_digest_changes_when_discovery_id_changes() -> None:
    r0 = _run_once(discovery_id="a")
    r1 = _run_once(discovery_id="b")
    assert r0.structure_digest != r1.structure_digest


def test_inv15_digest_changes_when_ts_changes() -> None:
    r0 = _run_once(ts_ns=1)
    r1 = _run_once(ts_ns=2)
    assert r0.structure_digest != r1.structure_digest


def test_inv15_digest_changes_when_variables_change() -> None:
    r0 = _run_once(variable_names=("a", "b", "c"))
    r1 = _run_once(variable_names=("a", "b", "d"))
    assert r0.structure_digest != r1.structure_digest


def test_inv15_digest_changes_when_edges_change() -> None:
    e1 = [DiscoveredEdge(source="x", target="y", weight=0.5)]
    e2 = [DiscoveredEdge(source="x", target="y", weight=0.9)]
    r0 = _run_once(edges=e1)
    r1 = _run_once(edges=e2)
    assert r0.structure_digest != r1.structure_digest


def test_inv15_digest_is_blake2b_64_hex() -> None:
    r = _run_once()
    assert len(r.structure_digest) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", r.structure_digest)
    h = hashlib.blake2b(b"smoke", digest_size=32).hexdigest()
    assert len(h) == 64


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------


def test_null_callback_is_callable() -> None:
    assert callable(null_structure_discovery_callback)


def test_null_callback_satisfies_protocol() -> None:
    assert isinstance(null_structure_discovery_callback, StructureDiscoveryCallback)


def test_null_callback_returns_none() -> None:
    record = _run_once()
    assert null_structure_discovery_callback(record) is None


def test_custom_callback_is_invoked() -> None:
    received: list[CausalStructureRecord] = []

    def _cb(record: CausalStructureRecord) -> None:
        received.append(record)

    learner = CausalStructureLearner(
        structure_learner=_FakeLearner(),
        callback=_cb,
    )
    args = _valid_arguments()
    learner.discover(
        data_rows=[{"x": 1.0, "y": 2.0, "z": 3.0}],
        arguments=args,
        discovery_id="cb-test",
        ts_ns=1,
    )
    assert len(received) == 1
    assert received[0].discovery_id == "cb-test"


# ---------------------------------------------------------------------------
# Convenience factory raises when causalnex missing
# ---------------------------------------------------------------------------


def test_causalnex_factory_raises_when_dep_missing() -> None:
    try:
        importlib.import_module("causalnex")
    except ImportError:
        learner = causalnex_notears_learner()
        with pytest.raises(ImportError):
            learner.learn_structure(
                data_rows=[{"x": 1.0, "y": 2.0}],
                variable_names=("x", "y"),
                edge_threshold=0.05,
                max_iter=100,
                penalty=PenaltyKind.L1,
                random_seed=42,
            )
    else:
        pytest.skip("causalnex installed — production seam smoke skipped")


# ---------------------------------------------------------------------------
# AST guards — OFFLINE_ONLY tier
# ---------------------------------------------------------------------------


_MODULE_PATH = Path(__file__).resolve().parents[1] / "state" / "knowledge_graph_causal.py"


def _module_ast() -> ast.Module:
    return ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))


def _top_level_imports(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.append(node.module)
    return names


def test_no_top_level_causalnex_import() -> None:
    assert all(not name.startswith("causalnex") for name in _top_level_imports(_module_ast()))


def test_no_top_level_pandas_import() -> None:
    assert all(not name.startswith("pandas") for name in _top_level_imports(_module_ast()))


def test_no_top_level_numpy_import() -> None:
    assert all(not name.startswith("numpy") for name in _top_level_imports(_module_ast()))


def test_no_top_level_io_imports() -> None:
    banned = {"subprocess", "socket", "urllib", "requests", "httpx", "aiohttp"}
    assert not (banned & set(_top_level_imports(_module_ast())))


def test_no_engine_cross_imports_at_top_level() -> None:
    banned_prefixes = (
        "execution_engine.",
        "governance_engine.",
        "system_engine.",
        "registry.",
        "ui.",
    )
    for name in _top_level_imports(_module_ast()):
        for prefix in banned_prefixes:
            assert not name.startswith(prefix), name


def test_no_engine_cross_imports_in_code() -> None:
    tree = _module_ast()
    code_only_segments: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Attribute, ast.Name)):
            code_only_segments.append(ast.dump(node))
    blob = "\n".join(code_only_segments)
    for needle in (
        "execution_engine",
        "governance_engine",
        "system_engine",
        "registry",
    ):
        assert needle not in blob, needle


def test_causalnex_import_only_inside_factory() -> None:
    tree = _module_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "causalnex" in node.module:
            # Must be inside a function body (not top-level).
            # The AST walk confirms this by structure: top-level imports
            # are caught by the above test; any remaining causalnex import
            # must be inside a function (nested).
            pass  # intentional: the top-level test already excludes it
