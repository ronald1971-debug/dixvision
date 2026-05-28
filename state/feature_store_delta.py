# ADAPTED FROM: delta-io/delta-rs (Python bindings)
# (deltalake/table.py — DeltaTable class, version(), history(), load_as_version();
#  deltalake/writer.py — write_deltalake() with mode="append"/"overwrite";
#  pyarrow integration for columnar read/write)
"""C-54 — DeltaLake ACID feature store.

This module adapts the ``deltalake`` Python library (Rust-backed) for
ACID-compliant feature storage with time-travel (versioned reads).

What survives from upstream (delta-io/delta-rs):
    * **DeltaTable** — ``table.py``: ``DeltaTable(path)`` for reading,
      ``.version()``, ``.history()``, ``.load_as_version(v)`` for
      time-travel.
    * **write_deltalake** — ``writer.py``: ``write_deltalake(path, df,
      mode="append"|"overwrite")`` for ACID writes.
    * **PyArrow integration** — ``to_pyarrow_table()`` /
      ``to_pandas()`` for columnar access.

What we replaced:
    * Real ``deltalake`` import is lazy (Protocol seam).
    * In-memory dict-of-lists for unit tests.
    * Same ``get_online_features`` interface as ``state/feature_store.py``.

OFFLINE tier: writes are batch (ACID transactions).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FeatureRow:
    """A single feature row in the delta store."""

    entity_key: str
    features: Mapping[str, float | int | str] = field(default_factory=dict)
    event_timestamp_ns: int = 0


class DeltaFeatureStore:
    """ACID feature store backed by Delta Lake format.

    Mirrors ``DeltaTable`` read patterns and ``write_deltalake()`` for
    writes. Supports time-travel (versioned reads).

    In test mode (default), buffers features in-memory.
    """

    def __init__(
        self,
        *,
        table_path: str = "",
        in_memory: bool = True,
    ) -> None:
        self._table_path = table_path
        self._in_memory = in_memory
        self._buffer: list[FeatureRow] = []
        self._versions: list[list[FeatureRow]] = [[]]

    def write_features(
        self,
        rows: Sequence[FeatureRow],
        *,
        mode: str = "append",
    ) -> int:
        """Write feature rows to the delta table.

        Args:
            rows: Feature rows to write.
            mode: "append" or "overwrite".

        Returns:
            Number of rows written.
        """
        if self._in_memory:
            if mode == "overwrite":
                self._buffer = list(rows)
            else:
                self._buffer.extend(rows)
            self._versions.append(list(self._buffer))
            return len(rows)
        return self._write_delta(rows, mode)

    def get_online_features(
        self,
        entity_keys: Sequence[str],
        feature_names: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve latest features for given entity keys.

        Mirrors Feast's ``get_online_features`` interface.
        """
        if self._in_memory:
            return self._get_from_buffer(entity_keys, feature_names)
        return self._get_from_delta(entity_keys, feature_names)

    def version(self) -> int:
        """Return current table version (number of commits)."""
        if self._in_memory:
            return len(self._versions) - 1
        try:
            from deltalake import DeltaTable

            dt = DeltaTable(self._table_path)
            return dt.version()
        except ImportError:
            return 0

    def load_as_version(self, v: int) -> list[FeatureRow]:
        """Time-travel: load features at a specific version."""
        if self._in_memory:
            if 0 <= v < len(self._versions):
                return list(self._versions[v])
            return []
        try:
            from deltalake import DeltaTable

            dt = DeltaTable(self._table_path, version=v)
            table = dt.to_pyarrow_table()
            rows: list[FeatureRow] = []
            for i in range(len(table)):
                row = table.slice(i, 1).to_pydict()
                rows.append(
                    FeatureRow(
                        entity_key=str(row.get("entity_key", [""])[0]),
                        features={
                            k: v[0]
                            for k, v in row.items()
                            if k not in ("entity_key", "event_timestamp_ns")
                        },
                    )
                )
            return rows
        except ImportError:
            return []

    def row_count(self) -> int:
        """Return number of rows in the current version."""
        return len(self._buffer)

    # ---- internals -------------------------------------------------------

    def _get_from_buffer(
        self,
        entity_keys: Sequence[str],
        feature_names: Sequence[str] | None,
    ) -> list[dict[str, Any]]:
        key_set = set(entity_keys)
        results: list[dict[str, Any]] = []
        seen: dict[str, dict[str, Any]] = {}
        for row in reversed(self._buffer):
            if row.entity_key in key_set and row.entity_key not in seen:
                entry: dict[str, Any] = {"entity_key": row.entity_key}
                if feature_names:
                    for fn in feature_names:
                        entry[fn] = row.features.get(fn)
                else:
                    entry.update(row.features)
                seen[row.entity_key] = entry
        for ek in entity_keys:
            results.append(seen.get(ek, {"entity_key": ek}))
        return results

    def _write_delta(self, rows: Sequence[FeatureRow], mode: str) -> int:
        """Write via deltalake library."""
        try:
            import pyarrow as pa
            from deltalake import write_deltalake

            data = {
                "entity_key": [r.entity_key for r in rows],
                "event_timestamp_ns": [r.event_timestamp_ns for r in rows],
            }
            all_keys: set[str] = set()
            for r in rows:
                all_keys.update(r.features.keys())
            for key in sorted(all_keys):
                data[key] = [r.features.get(key) for r in rows]
            table = pa.table(data)
            write_deltalake(self._table_path, table, mode=mode)
            return len(rows)
        except ImportError:
            self._buffer.extend(rows)
            return len(rows)

    def _get_from_delta(
        self,
        entity_keys: Sequence[str],
        feature_names: Sequence[str] | None,
    ) -> list[dict[str, Any]]:
        """Read from delta table."""
        try:
            from deltalake import DeltaTable

            dt = DeltaTable(self._table_path)
            table = dt.to_pyarrow_table()
            df = table.to_pandas()
            results: list[dict[str, Any]] = []
            for ek in entity_keys:
                mask = df["entity_key"] == ek
                rows = df[mask]
                if len(rows) > 0:
                    row = rows.iloc[-1]
                    entry: dict[str, Any] = {"entity_key": ek}
                    cols = (
                        list(feature_names)
                        if feature_names
                        else [
                            c for c in df.columns if c not in ("entity_key", "event_timestamp_ns")
                        ]
                    )
                    for c in cols:
                        entry[c] = row.get(c)
                    results.append(entry)
                else:
                    results.append({"entity_key": ek})
            return results
        except ImportError:
            return self._get_from_buffer(entity_keys, feature_names)


__all__ = ["DeltaFeatureStore", "FeatureRow"]
