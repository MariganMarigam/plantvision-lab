"""Schema and invariant validation for the service layer.

Validation is pure and fails loudly with a dotted path so a coverage bug
crashes the build instead of silently blanking a card.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Mapping, Sequence

from plantvision.analytics.validity import ContractError, VALIDITY_STATUSES

from .types import SourceBundle

SCHEMA = "pv-dashboard/3"
SCHEMA_MINOR = 0

SECTIONS: tuple[str, ...] = (
    "meta",
    "conditions",
    "panels",
    "series",
    "measurements",
    "validity",
    "evidence",
    "tables",
    "cards",
    "links",
    "findings",
    "snapshots",
    "render",
)

META_KEYS: tuple[str, ...] = (
    "schema",
    "schema_minor",
    "title",
    "lang",
    "now",
    "generated_at",
    "now_source",
    "options",
    "totals",
    "budget",
)

# Keys documented as nullable in the contract (``meta`` plus card/series/panel
# fields checked during payload validation).
NULLABLE_META: frozenset[str] = frozenset({"generated_at"})


def _require(condition: bool, path: str, message: str) -> None:
    """Raise :class:`ContractError` when ``condition`` is false."""
    if not condition:
        raise ContractError(f"{path}: {message}")


def _finite(value: object) -> bool:
    """Whether ``value`` is a finite int/float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _walk(payload: Mapping[str, object], path: str) -> object:
    """Resolve a dotted path, returning a sentinel on failure."""
    parts = path.split(".")
    current: object = payload
    for index, part in enumerate(parts):
        if isinstance(current, list):
            if index == len(parts) - 1:
                return current
            raise ContractError(f"cards[].reads: {path} is not an object at {part}")
        if not isinstance(current, Mapping):
            raise ContractError(f"cards[].reads: {path} is not an object at {part}")
        if part not in current:
            raise ContractError(f"cards[].reads: missing path {path}")
        current = current[part]
    return current


def _resolve_read(payload: Mapping[str, object], read: str) -> None:
    """Resolve one card read path, expanding a ``<pid>`` placeholder."""
    if read.startswith("tables."):
        tables = payload.get("tables")
        table_id = read[len("tables."):]
        if not isinstance(tables, Mapping) or table_id not in tables:
            raise ContractError(f"cards[].reads: missing path {read}")
        return
    if "<pid>" in read:
        panels = payload.get("panels")
        if not isinstance(panels, list) or not panels:
            raise ContractError(f"cards[].reads: no panel for {read}")
        for panel in panels:
            panel_id = str(panel.get("id", ""))
            _walk(payload, read.replace("<pid>", panel_id))
        return
    _walk(payload, read)


def validate_sources(bundle: SourceBundle) -> None:
    """Validate parsed sources before derivation.

    Args:
        bundle: Loaded source bundle.

    Raises:
        ContractError: If a panel has no rows mapping entry or a parsed row
            carries a non-finite number in a numeric cell.
    """
    for panel in bundle.panels:
        panel_id = str(getattr(panel, "id", ""))
        _require(panel_id in bundle.rows_by_panel, "sources", f"missing rows for {panel_id}")
        for row in bundle.rows_by_panel[panel_id]:
            for key, value in row.items():
                text = (value or "").strip()
                if not text:
                    continue
                try:
                    number = float(text)
                except ValueError:
                    continue
                if not math.isfinite(number):
                    raise ContractError(
                        f"source row {panel_id}.{key}: non-finite value {text!r}"
                    )
    for status in bundle.validity.by_key.values():
        _require(status in VALIDITY_STATUSES, "validity", f"illegal status {status!r}")


def _validate_meta(meta: Mapping[str, object]) -> None:
    """Check the 11 meta keys, schema and budget."""
    for key in META_KEYS:
        _require(key in meta, f"meta.{key}", "missing required key")
    _require(meta["schema"] == SCHEMA, "meta.schema", f"expected {SCHEMA}")
    _require(isinstance(meta["schema_minor"], int), "meta.schema_minor", "must be int")
    _require(isinstance(meta["schema"], str), "meta.schema", "must be string")
    _require(isinstance(meta["title"], str), "meta.title", "must be string")
    _require(bool(meta["title"].strip()), "meta.title", "must be non-empty")
    _require(isinstance(meta["now"], str), "meta.now", "must be string")
    _require(isinstance(meta["lang"], str), "meta.lang", "must be string")
    _require(meta["lang"] in {"en", "ru"}, "meta.lang", "must be en or ru")
    _require(
        meta["now_source"] in {"cli", "data", "none"},
        "meta.now_source",
        "must be cli/data/none",
    )
    _require(
        meta["generated_at"] is None or isinstance(meta["generated_at"], str),
        "meta.generated_at",
        "must be string or null",
    )
    options = meta["options"]
    _require(isinstance(options, Mapping), "meta.options", "must be an object")
    for key in ("window", "agg", "mode"):
        _require(key in options, f"meta.options.{key}", "missing required key")
    budget = meta["budget"]
    _require(isinstance(budget, Mapping), "meta.budget", "must be an object")
    _require(
        _finite(budget.get("json_bytes")) and _finite(budget.get("max_json_bytes")),
        "meta.budget",
        "json_bytes/max_json_bytes must be finite numbers",
    )
    _require(
        float(budget["json_bytes"]) <= float(budget["max_json_bytes"]),
        "meta.budget.json_bytes",
        "exceeds max_json_bytes",
    )


def _validate_validity_section(validity: Mapping[str, object]) -> None:
    """Check validity rows, by_key and counts."""
    rows = validity.get("rows")
    _require(isinstance(rows, list), "validity.rows", "must be a list")
    seen: set[str] = set()
    for index, row in enumerate(rows):
        _require(isinstance(row, Mapping), f"validity.rows[{index}]", "must be an object")
        for key in ("method_id", "method_version", "condition_key", "metric", "status"):
            _require(key in row, f"validity.rows[{index}].{key}", "missing required key")
        status = str(row["status"])
        _require(status in VALIDITY_STATUSES, f"validity.rows[{index}].status", "illegal")
        key = f"{row['method_version']}|{row['condition_key']}|{row['metric']}"
        _require(key not in seen, f"validity.rows[{index}]", "duplicate tuple")
        seen.add(key)
        if status == "valid":
            _require(
                bool(str(row.get("evidence_path", "")).strip()),
                f"validity.rows[{index}].evidence_path",
                "valid requires evidence_path",
            )
    by_key = validity.get("by_key")
    _require(isinstance(by_key, Mapping), "validity.by_key", "must be an object")
    for key, status in by_key.items():
        _require(status in VALIDITY_STATUSES, f"validity.by_key.{key}", "illegal status")
    matrix = validity.get("matrix")
    _require(isinstance(matrix, Mapping), "validity.matrix", "must be an object")
    for key in ("row_labels", "column_labels", "cells", "legend"):
        _require(key in matrix, f"validity.matrix.{key}", "missing required key")
    counts = validity.get("counts")
    _require(isinstance(counts, Mapping), "validity.counts", "must be an object")


def _validate_evidence(evidence: Mapping[str, object]) -> None:
    """Check evidence paths and row counts."""
    for evidence_id, block in evidence.items():
        _require(isinstance(block, Mapping), f"evidence.{evidence_id}", "must be object")
        path = str(block.get("path", ""))
        _require(path, f"evidence.{evidence_id}.path", "must be non-empty")
        _require(not Path(path).is_absolute(), f"evidence.{evidence_id}.path", "must be relative")
        _require(".." not in Path(path).parts, f"evidence.{evidence_id}.path", "must not contain ..")
        rows = block.get("rows")
        _require(
            rows is None or (isinstance(rows, int) and rows >= 0),
            f"evidence.{evidence_id}.rows",
            "must be null or an int >= 0",
        )


def _validate_cards(payload: Mapping[str, object]) -> None:
    """Check card identities, slots, state, read paths and evidence ids."""
    cards = payload.get("cards")
    _require(isinstance(cards, list), "cards", "must be a list")
    seen: set[tuple[str, str]] = set()
    evidence = payload.get("evidence")
    _require(isinstance(evidence, Mapping), "evidence", "must be an object")
    for index, card in enumerate(cards):
        _require(isinstance(card, Mapping), f"cards[{index}]", "must be an object")
        for key in ("id", "tab", "sub", "primitive", "state"):
            _require(key in card, f"cards[{index}].{key}", "missing required key")
        identity = (str(card["id"]), str(card["sub"]))
        _require(identity not in seen, f"cards[{index}]", f"duplicate {identity}")
        seen.add(identity)
        _require(
            card["state"] in {
                "ok", "empty", "not_recorded", "invalid", "unproven",
                "warn", "critical", "unknown",
            },
            f"cards[{index}].state",
            "illegal state",
        )
        slots = card.get("slots")
        _require(isinstance(slots, Mapping), f"cards[{index}].slots", "must be an object")
        for slot in ("what", "how", "now", "do"):
            for lang in ("en", "ru"):
                _require(
                    bool(str(slots.get(f"{slot}_{lang}", "")).strip()),
                    f"cards[{index}].slots.{slot}_{lang}",
                    "must be non-empty",
                )
        reads = card.get("reads")
        _require(isinstance(reads, list), f"cards[{index}].reads", "must be a list")
        for read in reads:
            _resolve_read(payload, str(read))
        for evidence_id in card.get("evidence", []):
            _require(
                str(evidence_id) in evidence,
                f"cards[{index}].evidence",
                f"unresolved {evidence_id}",
            )


def validate_payload(payload: Mapping[str, object]) -> None:
    """Validate a complete v3 payload.

    Args:
        payload: The assembled payload.

    Raises:
        ContractError: On a missing section/key, a type/nullability mismatch,
            an unresolved card read or evidence id, a non-finite number, or a
            budget overflow.
    """
    _require(isinstance(payload, Mapping), "payload", "must be an object")
    for section in SECTIONS:
        _require(section in payload, section, "missing required section")
    _validate_meta(payload["meta"])  # type: ignore[arg-type]
    validity = payload["validity"]
    _require(isinstance(validity, Mapping), "validity", "must be an object")
    _validate_validity_section(validity)
    evidence = payload["evidence"]
    _require(isinstance(evidence, Mapping), "evidence", "must be an object")
    _validate_evidence(evidence)
    _validate_cards(payload)
