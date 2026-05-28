"""tools/contract_diff.py
DIX VISION v42.2 — Contract Diff Tool

Compares two versions of a contract (frozen dataclass) and produces
a structured diff showing added, removed, and changed fields.

Usage:
    python tools/contract_diff.py <module.ClassName> <old_commit> <new_commit>

    or as a library:
        from tools.contract_diff import diff_contracts, ContractDiff
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import importlib
import sys
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FieldChange:
    """A single field change between two contract versions."""
    field_name: str
    change_kind: str        # ADDED | REMOVED | TYPE_CHANGED | DEFAULT_CHANGED
    old_type: str
    new_type: str
    old_default: str
    new_default: str


@dataclass(frozen=True, slots=True)
class ContractDiff:
    """Diff result between two contract class definitions."""
    class_name: str
    module: str
    added_fields: tuple[FieldChange, ...]
    removed_fields: tuple[FieldChange, ...]
    changed_fields: tuple[FieldChange, ...]
    is_frozen_before: bool
    is_frozen_after: bool
    breaking: bool    # True if fields removed or types narrowed

    @property
    def has_changes(self) -> bool:
        return bool(self.added_fields or self.removed_fields or self.changed_fields)


def _extract_fields(cls: type) -> dict[str, tuple[str, str]]:
    """Extract {field_name: (type_str, default_str)} from a dataclass."""
    if not dataclasses.is_dataclass(cls):
        return {}
    result: dict[str, tuple[str, str]] = {}
    for f in dataclasses.fields(cls):
        type_str = str(f.type) if f.type != dataclasses.MISSING else "Any"
        if f.default is not dataclasses.MISSING:
            default_str = repr(f.default)
        elif f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
            default_str = f"<factory:{f.default_factory}>"
        else:
            default_str = "<required>"
        result[f.name] = (type_str, default_str)
    return result


def diff_contract_classes(
    old_cls: type,
    new_cls: type,
) -> ContractDiff:
    """Diff two dataclass types and return a ContractDiff."""
    old_fields = _extract_fields(old_cls)
    new_fields = _extract_fields(new_cls)

    added: list[FieldChange] = []
    removed: list[FieldChange] = []
    changed: list[FieldChange] = []

    for name in new_fields:
        if name not in old_fields:
            ntype, ndefault = new_fields[name]
            added.append(FieldChange(
                field_name=name,
                change_kind="ADDED",
                old_type="",
                new_type=ntype,
                old_default="",
                new_default=ndefault,
            ))

    for name in old_fields:
        if name not in new_fields:
            otype, odefault = old_fields[name]
            removed.append(FieldChange(
                field_name=name,
                change_kind="REMOVED",
                old_type=otype,
                new_type="",
                old_default=odefault,
                new_default="",
            ))
        else:
            otype, odefault = old_fields[name]
            ntype, ndefault = new_fields[name]
            if otype != ntype:
                changed.append(FieldChange(
                    field_name=name,
                    change_kind="TYPE_CHANGED",
                    old_type=otype,
                    new_type=ntype,
                    old_default=odefault,
                    new_default=ndefault,
                ))
            elif odefault != ndefault:
                changed.append(FieldChange(
                    field_name=name,
                    change_kind="DEFAULT_CHANGED",
                    old_type=otype,
                    new_type=ntype,
                    old_default=odefault,
                    new_default=ndefault,
                ))

    old_frozen = getattr(old_cls, "__dataclass_params__", None)
    new_frozen = getattr(new_cls, "__dataclass_params__", None)
    old_is_frozen = getattr(old_frozen, "frozen", False) if old_frozen else False
    new_is_frozen = getattr(new_frozen, "frozen", False) if new_frozen else False

    breaking = bool(removed) or (old_is_frozen and not new_is_frozen)

    return ContractDiff(
        class_name=new_cls.__name__,
        module=getattr(new_cls, "__module__", "unknown"),
        added_fields=tuple(added),
        removed_fields=tuple(removed),
        changed_fields=tuple(changed),
        is_frozen_before=old_is_frozen,
        is_frozen_after=new_is_frozen,
        breaking=breaking,
    )


def format_diff(diff: ContractDiff) -> str:
    """Format a ContractDiff for human-readable display."""
    lines: list[str] = [
        f"Contract: {diff.module}.{diff.class_name}",
        f"Breaking: {'YES ⚠️' if diff.breaking else 'no'}",
        f"Frozen: {diff.is_frozen_before} → {diff.is_frozen_after}",
        "",
    ]
    if diff.added_fields:
        lines.append("ADDED:")
        for f in diff.added_fields:
            lines.append(f"  + {f.field_name}: {f.new_type} (default: {f.new_default})")
    if diff.removed_fields:
        lines.append("REMOVED:")
        for f in diff.removed_fields:
            lines.append(f"  - {f.field_name}: {f.old_type}")
    if diff.changed_fields:
        lines.append("CHANGED:")
        for f in diff.changed_fields:
            lines.append(f"  ~ {f.field_name}: {f.old_type} → {f.new_type}")
    if not diff.has_changes:
        lines.append("No changes detected.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Diff two contract class versions")
    parser.add_argument("old_module_class", help="old.module.ClassName")
    parser.add_argument("new_module_class", help="new.module.ClassName (may be same path)")
    args = parser.parse_args()

    def load_cls(spec: str) -> type:
        parts = spec.rsplit(".", 1)
        if len(parts) != 2:
            print(f"Invalid spec: {spec}", file=sys.stderr)
            sys.exit(1)
        mod = importlib.import_module(parts[0])
        return getattr(mod, parts[1])

    old_cls = load_cls(args.old_module_class)
    new_cls = load_cls(args.new_module_class)
    diff = diff_contract_classes(old_cls, new_cls)
    print(format_diff(diff))
    sys.exit(1 if diff.breaking else 0)


if __name__ == "__main__":
    main()


__all__ = ["ContractDiff", "FieldChange", "diff_contract_classes", "format_diff"]
