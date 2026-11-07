"""Measurement-validity records: load, look up and render the matrix.

Validity is a property of the tuple ``(method_version, condition_key, metric)``
rather than of a method alone. Missing tuples are ``unproven`` by default; a
valid record must name the evidence that supports it.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

VALIDITY_HEADER: tuple[str, ...] = (
    "method_id",
    "method_version",
    "condition_key",
    "metric",
    "status",
    "evidence_path",
    "evidence_rows",
    "evidence_from",
    "evidence_to",
    "date",
    "owner",
    "note",
)
VALIDITY_STATUSES: frozenset[str] = frozenset({"valid", "invalid", "unproven"})
CONDITION_ORDER: tuple[str, ...] = ("light", "crop", "rig", "scale", "pose")
LEGEND: dict[str, str] = {
    "valid": "✓",
    "invalid": "✕",
    "unproven": "?",
    "none": "",
}


class ContractError(ValueError):
    """Raised when a validity record or payload violates the contract."""


@dataclass(frozen=True)
class ValidityRecord:
    """One verdict for a method/condition/metric tuple."""

    method_id: str
    method_version: str
    condition_key: str
    metric: str
    status: str
    evidence_path: str = ""
    evidence_rows: int | None = None
    evidence_from: str = ""
    evidence_to: str = ""
    date: str = ""
    owner: str = ""
    note: str = ""

    @property
    def key(self) -> str:
        """Lookup key ``method_version|condition_key|metric``."""
        return f"{self.method_version}|{self.condition_key}|{self.metric}"

    @property
    def evidence_id(self) -> str:
        """Stable evidence id for the verdict."""
        return f"ev:validity:{self.method_id}|{self.condition_key}|{self.metric}"

    def as_json(self) -> dict[str, object]:
        """Return the payload row form."""
        return {
            "method_id": self.method_id,
            "method_version": self.method_version,
            "condition_key": self.condition_key,
            "metric": self.metric,
            "status": self.status,
            "evidence_id": self.evidence_id,
            "evidence_path": self.evidence_path,
            "evidence_rows": self.evidence_rows,
            "evidence_from": self.evidence_from,
            "evidence_to": self.evidence_to,
            "date": self.date,
            "owner": self.owner,
            "note": self.note,
        }


@dataclass(frozen=True)
class ValidityTable:
    """Validated validity records plus their lookup and counts."""

    records: tuple[ValidityRecord, ...] = ()
    by_key: Mapping[str, str] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        """Whether the table carries no record."""
        return not self.records

    def state(self, method_version: str, cond: str, metric: str) -> str:
        """Look up one tuple; a missing tuple is ``unproven`` (never valid)."""
        return self.by_key.get(f"{method_version}|{cond}|{metric}", "unproven")

    def counts(self) -> dict[str, int]:
        """Count records per status."""
        counts = {"valid": 0, "invalid": 0, "unproven": 0}
        for record in self.records:
            counts[record.status] += 1
        return counts


def _read_int(raw: str) -> int | None:
    """Parse an optional non-negative integer cell."""
    text = (raw or "").strip()
    if not text:
        return None
    try:
        value = int(text)
    except ValueError as exc:
        raise ContractError(f"evidence_rows must be an integer, got {text!r}") from exc
    if value < 0:
        raise ContractError(f"evidence_rows must be >= 0, got {value}")
    return value


def _sort_condition(cond: str) -> tuple[str, ...]:
    """Sort conditions by the fixed condition order."""
    parts = dict(
        item.split("=", 1) for item in cond.split("|") if "=" in item
    )
    return tuple(parts.get(name, "") for name in CONDITION_ORDER)


def load_validity(path: Path | None) -> ValidityTable:
    """Load and validate ``validity.csv``.

    Args:
        path: CSV path, or ``None``. A missing file yields an empty table so
            every lookup safely resolves to ``unproven``.

    Returns:
        The validated table with a ``method_version|condition|metric`` map.

    Raises:
        FileNotFoundError: If an explicitly configured path does not exist.
        ContractError: For a wrong header, illegal status, duplicate tuple, or
            a ``valid`` record without an evidence path.
    """
    if path is None:
        return ValidityTable()
    source = Path(path)
    if not source.exists():
        return ValidityTable()
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            header = tuple(next(reader))
        except StopIteration:
            return ValidityTable()
        if header != VALIDITY_HEADER:
            raise ContractError(
                f"validity header mismatch: file={header} expected={VALIDITY_HEADER}"
            )
        records: list[ValidityRecord] = []
        by_key: dict[str, str] = {}
        for line_number, cells in enumerate(reader, start=2):
            if not any(cell.strip() for cell in cells):
                continue
            if len(cells) != len(VALIDITY_HEADER):
                raise ContractError(
                    f"validity row {line_number}: expected {len(VALIDITY_HEADER)} "
                    f"columns, got {len(cells)}"
                )
            values = {name: cell.strip() for name, cell in zip(VALIDITY_HEADER, cells)}
            status = values["status"]
            if status not in VALIDITY_STATUSES:
                raise ContractError(
                    f"validity row {line_number}: illegal status {status!r}"
                )
            if status == "valid" and not values["evidence_path"]:
                raise ContractError(
                    f"validity row {line_number}: valid requires evidence_path"
                )
            record = ValidityRecord(
                method_id=values["method_id"],
                method_version=values["method_version"],
                condition_key=values["condition_key"],
                metric=values["metric"],
                status=status,
                evidence_path=values["evidence_path"],
                evidence_rows=_read_int(values["evidence_rows"]),
                evidence_from=values["evidence_from"],
                evidence_to=values["evidence_to"],
                date=values["date"],
                owner=values["owner"],
                note=values["note"],
            )
            if record.key in by_key:
                raise ContractError(
                    f"validity row {line_number}: duplicate tuple {record.key}"
                )
            by_key[record.key] = status
            records.append(record)
    records.sort(key=lambda r: (r.method_id, r.metric, r.condition_key))
    return ValidityTable(records=tuple(records), by_key=by_key)


def condition_key(row: Mapping[str, str]) -> str:
    """Compose the canonical, order-fixed condition key from a mapping.

    The order is always ``light, crop, rig, scale, pose``. Blank values are
    preserved as empty component values; the function never guesses a regime.

    Args:
        row: Mapping with ``light_regime``/``light``, ``crop``, ``rig``,
            ``scale`` and ``pose`` entries.

    Returns:
        ``light=<v>|crop=<v>|rig=<v>|scale=<v>|pose=<v>``.
    """
    def cell(*names: str) -> str:
        for name in names:
            value = (row.get(name) or "").strip()
            if value:
                return value
        return ""

    return "|".join(
        f"{name}={cell(name, 'light_regime') if name == 'light' else cell(name)}"
        for name in CONDITION_ORDER
    )


def validity_state(
    table: ValidityTable, method_version: str, cond: str, metric: str
) -> str:
    """Resolve one verdict; an absent tuple is ``unproven``.

    Args:
        table: Loaded validity table.
        method_version: Pipeline version stored on the CSV rows.
        cond: Canonical condition key.
        metric: Metric slug.

    Returns:
        ``valid``, ``invalid`` or ``unproven``.
    """
    return table.state(method_version, cond, metric)


def build_matrix(table: ValidityTable) -> dict[str, object]:
    """Build the method × metric × condition matrix.

    Args:
        table: Loaded validity table.

    Returns:
        ``row_labels``, ``column_labels``, ``cells`` and ``legend``. A cell is
        ``valid``/``invalid``/``unproven`` or ``None`` when no record exists.
    """
    columns = sorted(
        {record.condition_key for record in table.records},
        key=_sort_condition,
    )
    rows: dict[str, dict[str, str]] = {}
    for record in table.records:
        label = f"{record.method_id} · {record.metric}"
        rows.setdefault(label, {})[record.condition_key] = record.status
    row_labels = sorted(rows)
    cells = [
        [rows[label].get(column) for column in columns]
        for label in row_labels
    ]
    return {
        "row_labels": row_labels,
        "column_labels": columns,
        "cells": cells,
        "legend": dict(LEGEND),
    }


def records_for(
    table: ValidityTable, method_version: str, cond: str
) -> Sequence[ValidityRecord]:
    """Return records matching one method version and condition."""
    return tuple(
        record
        for record in table.records
        if record.method_version == method_version and record.condition_key == cond
    )


def finite(value: object) -> bool:
    """Whether a value is a finite number (used by the matrix tests)."""
    return isinstance(value, (int, float)) and math.isfinite(float(value))
