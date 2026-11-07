"""Validity record parsing, lookup and matrix contract tests (B0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plantvision.analytics.validity import (
    VALIDITY_HEADER,
    ContractError,
    build_matrix,
    condition_key,
    load_validity,
    validity_state,
)

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "derived" / "validity.csv"


def _write(path: Path, header: tuple[str, ...], rows: list[list[str]]) -> Path:
    """Write a small validity CSV with the supplied header/rows."""
    import csv

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def _seed_row(status: str = "invalid", evidence: str = "data/derived/metrics/farm04-timeseries.csv") -> list[str]:
    """One well-formed seed row."""
    return [
        "exg-40",
        "farm04-exg-0.1",
        "light=blurple|crop=lettuce|rig=farm-04|scale=aruco45|pose=side",
        "area_px",
        status,
        evidence,
        "457",
        "2026-11-03",
        "2026-11-05",
        "2026-11-07",
        "scout",
        "note",
    ]


def test_validity_header_fixed() -> None:
    table = load_validity(SEED)
    assert len(table.records) == 6
    assert VALIDITY_HEADER[0] == "method_id"
    reordered = _write(
        Path(test_validity_header_fixed.__name__ + ".csv"),
        (VALIDITY_HEADER[1], VALIDITY_HEADER[0], *VALIDITY_HEADER[2:]),
        [_seed_row()],
    )
    try:
        with pytest.raises(ContractError):
            load_validity(reordered)
    finally:
        reordered.unlink(missing_ok=True)


def test_duplicate_validity_row_fails(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "validity.csv",
        VALIDITY_HEADER,
        [_seed_row(), _seed_row()],
    )
    with pytest.raises(ContractError):
        load_validity(path)


def test_valid_row_requires_evidence(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "validity.csv",
        VALIDITY_HEADER,
        [_seed_row(status="valid", evidence="")],
    )
    with pytest.raises(ContractError):
        load_validity(path)


def test_missing_validity_defaults_unproven() -> None:
    table = load_validity(None)
    assert validity_state(table, "farm04-exg-0.1", "light=blurple", "area_px") == "unproven"
    assert load_validity(Path("does/not/exist.csv")).records == ()


def test_farm04_seed_verdicts() -> None:
    table = load_validity(SEED)
    blurple = "light=blurple|crop=lettuce|rig=farm-04|scale=aruco45|pose=side"
    white = "light=white|crop=lettuce|rig=farm-04|scale=aruco45|pose=side"
    assert validity_state(table, "farm04-exg-0.1", blurple, "area_px") == "invalid"
    assert validity_state(table, "farm04-exg-0.1", white, "area_px") == "valid"
    assert validity_state(table, "farm04-exg-0.1", blurple, "area_cm2") == "invalid"
    assert table.counts() == {"valid": 2, "invalid": 2, "unproven": 2}


def test_condition_key_is_order_fixed() -> None:
    key = condition_key(
        {
            "light": "white",
            "crop": "lettuce",
            "rig": "farm-04",
            "scale": "aruco45",
            "pose": "side",
        }
    )
    assert key == "light=white|crop=lettuce|rig=farm-04|scale=aruco45|pose=side"


def test_matrix_has_labels_cells_and_legend() -> None:
    matrix = build_matrix(load_validity(SEED))
    assert matrix["row_labels"] == [
        "exg-40 · area_cm2",
        "exg-40 · area_px",
        "hsv · area_px",
        "sam2 · solidity",
    ]
    assert len(matrix["column_labels"]) == 4
    assert matrix["legend"]["invalid"] == "✕"
    assert any("invalid" in column for column in matrix["cells"])
