# ADAPTED FROM: mckinsey/causalnex
# (causalnex/structure/notears.py — from_pandas NOTEARS continuous
#  structure-learning algorithm; causalnex/structure/structuremodel.py
#  — StructureModel directed graph for discovered causal edges.)
"""C-39 — CausalStructureLearner: governance-gated causal-graph
structure learning from observational market data.

CausalNex is McKinsey's causal-inference library built on the NOTEARS
algorithm (Zheng et al., 2018) — a continuous-optimisation approach to
Bayesian-network structure discovery. The ``from_pandas`` function
takes a DataFrame of observational variables and returns a directed
acyclic graph (DAG) representing discovered causal relationships.

What this module is
-------------------

* Pure-Python coordinator + frozen value objects. The actual
  ``causalnex`` / ``pandas`` / ``numpy`` imports are hidden behind a
  :class:`StructureLearner` Protocol — production code constructs a
  learner that lazy-imports causalnex inside
  :func:`causalnex_notears_learner`; unit tests inject a deterministic
  fake. The module never imports causalnex at module load.
* OFFLINE_ONLY tier. The learner reads no environment variables,
  performs no IO, never imports ``execution_engine`` /
  ``governance_engine`` / ``system_engine`` / ``registry`` / ``ui``.
  It produces one :class:`CausalStructureRecord` and stops.
* INV-15 byte-identical replays.
  :meth:`CausalStructureLearner.discover(...)` with identical
  ``arguments`` / ``ts_ns`` / ``discovery_id`` / ``learner`` returns
  identical :class:`CausalStructureRecord` records.
* No clock reads. Caller supplies ``ts_ns``.

What survives from upstream
---------------------------

* The NOTEARS continuous optimisation flow: ``from_pandas`` converts a
  DataFrame into a weighted adjacency matrix via L1-penalised
  least-squares DAG constraint. The DIX seam exposes this as a single
  :meth:`StructureLearner.learn_structure` call.
* The thresholding surface — :attr:`StructureArguments.edge_threshold`
  controls the minimum absolute weight below which discovered edges
  are pruned.
* The StructureModel directed graph output — flattened into a frozen
  list of :class:`DiscoveredEdge` value objects for deterministic
  storage into :mod:`state.knowledge_graph`.

What we replaced
----------------

* CausalNex's ``StructureModel`` NetworkX subclass → frozen
  :class:`DiscoveredEdge` value-object list. No mutable graph.
* CausalNex's visualisation utilities → no filesystem at all.
* CausalNex's Bayesian inference on the discovered structure →
  out-of-scope; the discovery output feeds into DoWhy (C-35) or
  PyMC (C-37) for inference.

Authority constraints (manifest §H1)
------------------------------------

* OFFLINE_ONLY tier — no IO, no clock, no global state, no PRNG reads
  from the wall clock; the learner's PRNG is seeded by caller-supplied
  :attr:`StructureArguments.random_seed`. AST tests pin the import
  contract.
* No engine cross-imports — AST test pins no ``execution_engine.`` /
  ``governance_engine.`` / ``system_engine.`` / ``registry.`` / ``ui.``
  references at any depth.
* INV-15 — :class:`CausalStructureRecord.structure_digest` is a
  deterministic function of the inputs (BLAKE2b over a canonical text
  projection). 3-run identical-input replay equality is pinned in tests.
* Defensive caps:
  - :data:`MAX_VARIABLES` 1000 hard ceiling on input variable count.
  - :data:`MAX_OBSERVATIONS` 10,000,000 hard ceiling on row count.
  - :data:`MAX_DISCOVERY_ID_LEN` 256 chars on caller-supplied
    ``discovery_id``.

Integration with :mod:`state.knowledge_graph`
---------------------------------------------

Discovered edges can be projected into the knowledge graph via the
standard :meth:`KnowledgeGraph.merge_caused_by` surface. This module
does NOT directly import or call knowledge_graph — the caller
(typically ``learning_engine``) bridges the two:

    record = learner.discover(args, ts_ns=…)
    for edge in record.edges:
        kg.merge_caused_by(src_id=edge.source, dst_id=edge.target,
                           weight=edge.weight, ts_ns=ts_ns)

Refs:
- ``DIX_MASTER_CANONICAL.md`` C-39 (causalnex structure learning spec).
- ``state/knowledge_graph.py`` (A-11 — the Neo4j knowledge store this
  module feeds into).
- ``core/causal_graph.py`` (A-12 — the in-process DAG this feeds).
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Module identity / dependency declaration.
# ---------------------------------------------------------------------------

NEW_PIP_DEPENDENCIES: tuple[str, ...] = ()
"""Live learner requires ``causalnex``; the Protocol seam allows fake
injection for tests (no deps)."""

STRUCTURE_SOURCE: str = "state.knowledge_graph_causal"
"""Constant tag stamped onto every emitted
:attr:`CausalStructureRecord.source`. The knowledge-graph projection
keys on this string to distinguish causalnex-produced records from
other structure-learning adapters."""

# ---------------------------------------------------------------------------
# Hard limits.
# ---------------------------------------------------------------------------

MIN_VARIABLES: int = 2
"""Minimum variable count — need at least 2 variables to discover edges."""

MAX_VARIABLES: int = 1_000
"""Hard upper bound on input variable count. NOTEARS is O(d^3) in the
number of variables; bounding prevents unbounded CPU allocation."""

MIN_OBSERVATIONS: int = 10
"""Minimum observation count — need statistical power."""

MAX_OBSERVATIONS: int = 10_000_000
"""Hard upper bound on input observation (row) count."""

MAX_DISCOVERY_ID_LEN: int = 256
"""Hard upper bound on caller-supplied :attr:`CausalStructureRecord.discovery_id`."""

MAX_DATA_DIGEST_LEN: int = 64
"""Hard upper bound on :attr:`StructureArguments.data_digest` length."""

MIN_EDGE_THRESHOLD: float = 0.0
"""Minimum edge threshold (no pruning)."""

MAX_EDGE_THRESHOLD: float = 10.0
"""Maximum edge threshold."""

MIN_MAX_ITER: int = 10
"""Minimum max iterations for the NOTEARS optimiser."""

MAX_MAX_ITER: int = 10_000
"""Maximum max iterations for the NOTEARS optimiser."""

DEFAULT_EDGE_THRESHOLD: float = 0.05
"""Default threshold below which discovered edge weights are pruned."""

DEFAULT_MAX_ITER: int = 100
"""Default max iterations for the NOTEARS optimiser."""

DEFAULT_RANDOM_SEED: int = 42
"""Default PRNG seed for reproducibility."""


# ---------------------------------------------------------------------------
# Penalty-type enum.
# ---------------------------------------------------------------------------


class PenaltyKind(enum.Enum):
    """NOTEARS penalty selector.

    Controls the sparsity penalty applied during structure learning.
    L1 produces sparser graphs; L2 retains more edges with lower
    weights; mixed applies both.
    """

    L1 = "l1"
    L2 = "l2"
    MIXED = "mixed"


# ---------------------------------------------------------------------------
# Frozen value objects.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class StructureArguments:
    """Immutable argument bundle for a structure-learning discovery.

    Attributes:
        variable_names: Ordered tuple of column/variable names.
        n_observations: Number of rows in the observational dataset.
        data_digest: Caller-computed digest of the input data (e.g.
            sha256 hex prefix). Used for INV-15 provenance tracking.
        edge_threshold: Minimum absolute edge weight to retain.
        max_iter: Maximum iterations for the NOTEARS optimiser.
        penalty: Sparsity penalty kind (L1/L2/mixed).
        random_seed: PRNG seed forwarded to numpy for reproducibility.
    """

    variable_names: tuple[str, ...]
    n_observations: int
    data_digest: str
    edge_threshold: float = DEFAULT_EDGE_THRESHOLD
    max_iter: int = DEFAULT_MAX_ITER
    penalty: PenaltyKind = PenaltyKind.L1
    random_seed: int = DEFAULT_RANDOM_SEED


@dataclasses.dataclass(frozen=True, slots=True)
class DiscoveredEdge:
    """One discovered causal edge from structure learning.

    Attributes:
        source: Source variable name (cause).
        target: Target variable name (effect).
        weight: Absolute edge weight from the NOTEARS W matrix.
    """

    source: str
    target: str
    weight: float


@dataclasses.dataclass(frozen=True, slots=True)
class CausalStructureRecord:
    """Immutable record of a completed structure-learning discovery.

    Attributes:
        discovery_id: Caller-supplied unique identifier for this run.
        source: Module provenance tag (:data:`STRUCTURE_SOURCE`).
        ts_ns: Caller-supplied nanosecond timestamp (no clock reads).
        arguments: The frozen argument bundle used for this run.
        edges: Discovered causal edges (sorted deterministically).
        n_edges_raw: Number of edges before threshold pruning.
        n_edges_pruned: Number of edges after threshold pruning.
        structure_digest: BLAKE2b hex digest over the canonical text
            projection of this record — deterministic on identical inputs.
    """

    discovery_id: str
    source: str
    ts_ns: int
    arguments: StructureArguments
    edges: tuple[DiscoveredEdge, ...]
    n_edges_raw: int
    n_edges_pruned: int
    structure_digest: str


# ---------------------------------------------------------------------------
# Protocol seam: StructureLearner.
# ---------------------------------------------------------------------------


@runtime_checkable
class StructureLearner(Protocol):
    """Protocol for causal-structure learners.

    Implementations hide the heavy-library import (causalnex / numpy /
    pandas) behind this seam. The coordinator (:class:`CausalStructureLearner`)
    calls :meth:`learn_structure` which returns a list of weighted edges.
    """

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
        """Discover causal structure from observational data.

        Args:
            data_rows: Sequence of observation dicts (variable → float).
            variable_names: Ordered column names.
            edge_threshold: Minimum absolute weight to retain.
            max_iter: Max NOTEARS optimiser iterations.
            penalty: Sparsity penalty kind.
            random_seed: PRNG seed for reproducibility.

        Returns:
            Tuple of (discovered_edges, n_edges_before_pruning).
            Edges must be sorted by (source, target) for determinism.
        """
        ...


# ---------------------------------------------------------------------------
# Callback Protocol.
# ---------------------------------------------------------------------------


@runtime_checkable
class StructureDiscoveryCallback(Protocol):
    """Optional callback invoked after structure discovery completes.

    Default: :func:`null_structure_discovery_callback` (no-op).
    """

    def __call__(self, record: CausalStructureRecord) -> None: ...


def null_structure_discovery_callback(record: CausalStructureRecord) -> None:
    """No-op callback — default when no observer is attached."""


# ---------------------------------------------------------------------------
# Config error.
# ---------------------------------------------------------------------------


class CausalStructureConfigError(ValueError):
    """Raised when :class:`StructureArguments` violates hard limits."""


# ---------------------------------------------------------------------------
# Coordinator: CausalStructureLearner.
# ---------------------------------------------------------------------------


class CausalStructureLearner:
    """Governance-gated causal-structure discovery coordinator.

    This class orchestrates the NOTEARS structure-learning flow:
    validate arguments → delegate to the :class:`StructureLearner`
    Protocol seam → build a frozen :class:`CausalStructureRecord`.

    Usage::

        learner = CausalStructureLearner(
            structure_learner=causalnex_notears_learner(),
        )
        record = learner.discover(
            data_rows=[{"x": 1.0, "y": 2.0, "z": 3.0}, ...],
            arguments=StructureArguments(
                variable_names=("x", "y", "z"),
                n_observations=100,
                data_digest="abc123",
            ),
            discovery_id="disc-001",
            ts_ns=1_000_000_000,
        )
        # record.edges → discovered causal edges
    """

    __slots__ = ("_learner", "_callback")

    def __init__(
        self,
        *,
        structure_learner: StructureLearner,
        callback: StructureDiscoveryCallback = null_structure_discovery_callback,
    ) -> None:
        self._learner = structure_learner
        self._callback = callback

    def discover(
        self,
        data_rows: Sequence[Mapping[str, float]],
        *,
        arguments: StructureArguments,
        discovery_id: str,
        ts_ns: int,
    ) -> CausalStructureRecord:
        """Run structure discovery and return a frozen record.

        Args:
            data_rows: Observational data as a sequence of dicts.
            arguments: Validated argument bundle.
            discovery_id: Caller-supplied unique identifier.
            ts_ns: Caller-supplied nanosecond timestamp.

        Returns:
            Frozen :class:`CausalStructureRecord` with discovered edges.

        Raises:
            CausalStructureConfigError: If arguments violate hard limits.
        """
        self._validate(arguments, discovery_id)

        edges, n_raw = self._learner.learn_structure(
            data_rows,
            arguments.variable_names,
            edge_threshold=arguments.edge_threshold,
            max_iter=arguments.max_iter,
            penalty=arguments.penalty,
            random_seed=arguments.random_seed,
        )

        # Sort edges deterministically for INV-15.
        sorted_edges = tuple(sorted(edges, key=lambda e: (e.source, e.target)))

        record = CausalStructureRecord(
            discovery_id=discovery_id,
            source=STRUCTURE_SOURCE,
            ts_ns=ts_ns,
            arguments=arguments,
            edges=sorted_edges,
            n_edges_raw=n_raw,
            n_edges_pruned=len(sorted_edges),
            structure_digest=_compute_digest(
                discovery_id=discovery_id,
                ts_ns=ts_ns,
                arguments=arguments,
                edges=sorted_edges,
            ),
        )

        self._callback(record)
        return record

    @staticmethod
    def _validate(arguments: StructureArguments, discovery_id: str) -> None:
        """Enforce hard limits on arguments."""
        if len(discovery_id) > MAX_DISCOVERY_ID_LEN:
            raise CausalStructureConfigError(
                f"discovery_id length {len(discovery_id)} exceeds "
                f"MAX_DISCOVERY_ID_LEN={MAX_DISCOVERY_ID_LEN}"
            )
        if not discovery_id:
            raise CausalStructureConfigError("discovery_id must not be empty")

        n_vars = len(arguments.variable_names)
        if n_vars < MIN_VARIABLES:
            raise CausalStructureConfigError(
                f"variable count {n_vars} < MIN_VARIABLES={MIN_VARIABLES}"
            )
        if n_vars > MAX_VARIABLES:
            raise CausalStructureConfigError(
                f"variable count {n_vars} > MAX_VARIABLES={MAX_VARIABLES}"
            )

        if arguments.n_observations < MIN_OBSERVATIONS:
            raise CausalStructureConfigError(
                f"n_observations {arguments.n_observations} < MIN_OBSERVATIONS={MIN_OBSERVATIONS}"
            )
        if arguments.n_observations > MAX_OBSERVATIONS:
            raise CausalStructureConfigError(
                f"n_observations {arguments.n_observations} > MAX_OBSERVATIONS={MAX_OBSERVATIONS}"
            )

        if len(arguments.data_digest) > MAX_DATA_DIGEST_LEN:
            raise CausalStructureConfigError(
                f"data_digest length {len(arguments.data_digest)} > "
                f"MAX_DATA_DIGEST_LEN={MAX_DATA_DIGEST_LEN}"
            )
        if not arguments.data_digest:
            raise CausalStructureConfigError("data_digest must not be empty")

        if not (MIN_EDGE_THRESHOLD <= arguments.edge_threshold <= MAX_EDGE_THRESHOLD):
            raise CausalStructureConfigError(
                f"edge_threshold {arguments.edge_threshold} out of range "
                f"[{MIN_EDGE_THRESHOLD}, {MAX_EDGE_THRESHOLD}]"
            )

        if not (MIN_MAX_ITER <= arguments.max_iter <= MAX_MAX_ITER):
            raise CausalStructureConfigError(
                f"max_iter {arguments.max_iter} out of range [{MIN_MAX_ITER}, {MAX_MAX_ITER}]"
            )

        if not isinstance(arguments.penalty, PenaltyKind):
            raise CausalStructureConfigError(
                f"penalty must be PenaltyKind, got {type(arguments.penalty).__name__}"
            )

        # Validate variable names are non-empty unique strings.
        seen: set[str] = set()
        for name in arguments.variable_names:
            if not name:
                raise CausalStructureConfigError("variable names must be non-empty")
            if name in seen:
                raise CausalStructureConfigError(f"duplicate variable name: {name!r}")
            seen.add(name)


# ---------------------------------------------------------------------------
# Digest computation (INV-15).
# ---------------------------------------------------------------------------


def _compute_digest(
    *,
    discovery_id: str,
    ts_ns: int,
    arguments: StructureArguments,
    edges: tuple[DiscoveredEdge, ...],
) -> str:
    """Compute a deterministic BLAKE2b digest over the canonical projection.

    INV-15: identical inputs → identical digest. No floating-point
    instability — edge weights are formatted to 12 decimal places.
    """
    parts: list[str] = [
        f"discovery_id={discovery_id}",
        f"ts_ns={ts_ns}",
        f"variables={','.join(arguments.variable_names)}",
        f"n_observations={arguments.n_observations}",
        f"data_digest={arguments.data_digest}",
        f"edge_threshold={arguments.edge_threshold:.12f}",
        f"max_iter={arguments.max_iter}",
        f"penalty={arguments.penalty.value}",
        f"random_seed={arguments.random_seed}",
    ]
    for edge in edges:
        parts.append(f"edge={edge.source}->{edge.target}:{edge.weight:.12f}")

    canonical = "\n".join(parts)
    return hashlib.blake2b(canonical.encode("utf-8"), digest_size=32).hexdigest()


# ---------------------------------------------------------------------------
# CausalNex NOTEARS factory (lazy import).
# ---------------------------------------------------------------------------


def causalnex_notears_learner() -> StructureLearner:
    """Factory returning a :class:`StructureLearner` backed by CausalNex.

    The ``causalnex`` package is imported lazily inside the returned
    object's :meth:`learn_structure` method — never at module load.
    This keeps the module importable in environments that lack
    causalnex (tests, lint, authority checks).
    """
    return _CausalNexNOTEARS()


class _CausalNexNOTEARS:
    """StructureLearner implementation using CausalNex NOTEARS."""

    __slots__ = ()

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
        """Run NOTEARS via causalnex.structure.notears.from_pandas."""
        import numpy as np  # noqa: PLC0415, I001
        import pandas as pd  # noqa: PLC0415, I001
        from causalnex.structure.notears import from_pandas  # noqa: PLC0415, I001

        # Seed numpy PRNG for determinism (INV-15).
        np.random.seed(random_seed)  # noqa: NPY002

        # Build DataFrame from observations.
        df = pd.DataFrame(list(data_rows), columns=list(variable_names))

        # Run NOTEARS structure learning.
        sm = from_pandas(
            df,
            max_iter=max_iter,
            w_threshold=0.0,  # Get all edges first, prune below.
            tabu_edges=None,
            tabu_parent_nodes=None,
            tabu_child_nodes=None,
        )

        # Extract all edges before pruning.
        all_edges = list(sm.edges(data=True))
        n_raw = len(all_edges)

        # Prune by threshold and build DiscoveredEdge list.
        discovered: list[DiscoveredEdge] = []
        for source, target, data in all_edges:
            weight = abs(float(data.get("weight", 0.0)))
            if weight >= edge_threshold:
                discovered.append(
                    DiscoveredEdge(
                        source=str(source),
                        target=str(target),
                        weight=weight,
                    )
                )

        # Sort for determinism.
        discovered.sort(key=lambda e: (e.source, e.target))
        return discovered, n_raw


# ---------------------------------------------------------------------------
# __all__ export surface.
# ---------------------------------------------------------------------------

__all__ = (
    "STRUCTURE_SOURCE",
    "CausalStructureConfigError",
    "CausalStructureLearner",
    "CausalStructureRecord",
    "DEFAULT_EDGE_THRESHOLD",
    "DEFAULT_MAX_ITER",
    "DEFAULT_RANDOM_SEED",
    "DiscoveredEdge",
    "MAX_DATA_DIGEST_LEN",
    "MAX_DISCOVERY_ID_LEN",
    "MAX_EDGE_THRESHOLD",
    "MAX_MAX_ITER",
    "MAX_OBSERVATIONS",
    "MAX_VARIABLES",
    "MIN_EDGE_THRESHOLD",
    "MIN_MAX_ITER",
    "MIN_OBSERVATIONS",
    "MIN_VARIABLES",
    "NEW_PIP_DEPENDENCIES",
    "PenaltyKind",
    "StructureArguments",
    "StructureDiscoveryCallback",
    "StructureLearner",
    "causalnex_notears_learner",
    "null_structure_discovery_callback",
)
