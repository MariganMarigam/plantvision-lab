"""Manifest build and deterministic splits (plan Section 6 Step 5)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from plantvision.labeling.store import (
    MANIFEST_COLUMNS,
    assign_splits,
    build_manifest,
    write_manifest_csv,
)


def _proposal(sha: str, captured_at: str, score: float = 0.9, group: str = "g0") -> dict:
    return {
        "sha256": sha,
        "frame_relpath": f"cam-a/zone/{captured_at[:10]}/{sha[:8]}.jpg",
        "mask_relpath": f"masks/{sha}.png",
        "score": score,
        "area_fraction": 0.10,
        "box": [1, 2, 3, 4],
        "box_source": "hsv",
        "model": "sam2.1_hiera_small",
        "checkpoint": "checkpoints/sam2.1_hiera_small.pt",
        "created_at": captured_at,
        "group_key": group,
        # build_manifest joining keys come from the proposal record itself:
        "captured_at_row": captured_at,  # unused, kept explicit in tests below
    }


def _plain_proposal(sha: str, captured_at: str, score: float = 0.9, group: str = "g0") -> dict:
    p = _proposal(sha, captured_at, score, group)
    p["captured_at"] = captured_at
    p.pop("captured_at_row")
    return p


def _rows(n: int, base_captured: str = "2026-10-16T10:00:00+00:00") -> list[dict]:
    return [
        _plain_proposal(f"{i:064x}", f"2026-10-{16 + 0}T{10 + i:02d}:00:00+00:00", group=f"g{i:02d}")
        for i in range(n)
    ]


def test_manifest_columns_exact() -> None:
    rows = build_manifest([_plain_proposal("a" * 64, "2026-10-16T10:00:00+00:00")], {})
    assert list(rows[0].keys()) == list(MANIFEST_COLUMNS)
    row = rows[0]
    assert row["sha256"] == "a" * 64
    assert row["accepted"] == ""
    assert row["reject_reason"] == ""
    assert row["reviewer"] == ""
    assert row["split"] in ("train", "val", "test", "")
    assert row["confidence"] == "0.9000"
    assert row["area_fraction"] == "0.1000"
    assert row["box"] == "1;2;3;4"
    assert row["box_source"] == "hsv"
    assert row["model"] == "sam2.1_hiera_small"
    assert row["group_key"] == "g0"
    assert row["captured_at"] == "2026-10-16T10:00:00+00:00"


def test_manifest_deterministic_and_input_order_independent() -> None:
    props = _rows(6)
    rows_a = build_manifest(props, {})
    rows_b = build_manifest(
        [copy.deepcopy(props[len(props) - 1 - i]) for i in range(len(props))], {}
    )
    assert rows_a == rows_b
    # input list is not mutated
    assert "split" not in props[0]
    # sorted by (captured_at, sha256): ascending timestamps
    stamps = [r["captured_at"] for r in rows_a]
    assert stamps == sorted(stamps)


@pytest.mark.parametrize(
    ("n", "expected"),
    [(59, (41, 8, 10)), (20, (14, 3, 3)), (10, (7, 1, 2)), (4, (2, 1, 1)),
     (3, (1, 1, 1)), (2, (2, 0, 0))],
)
def test_split_temporal_70_15_15(n: int, expected: tuple[int, int, int]) -> None:
    rows = _rows(n)
    rows = assign_splits(rows, strategy="temporal")
    counts = {s: sum(1 for r in rows if r["split"] == s)
              for s in ("train", "val", "test")}
    assert counts == dict(zip(("train", "val", "test"), expected)), (
        f"n={n}: {counts} != {expected}"
    )
    # contiguous: split is ordered train..train, val..val, test..test
    seen = [r["split"] for r in rows]
    assert seen == (
        ["train"] * expected[0] + ["val"] * expected[1] + ["test"] * expected[2]
    )


def test_split_small_dataset_all_train() -> None:
    rows = assign_splits(_rows(2), strategy="temporal")
    assert all(r["split"] == "train" for r in rows)


def test_accepted_flag_follows_last_decision() -> None:
    sha = "a" * 64
    decisions = {
        sha: {
            "verdict": "accept",
            "reason": "",
            "reviewer": "local",
            "decided_at": "2026-10-17T10:05:00+00:00",
        }
    }
    rows = build_manifest([_plain_proposal(sha, "2026-10-16T10:00:00+00:00",
                                           group="g1"),
                           _plain_proposal("b" * 64, "2026-10-16T11:00:00+00:00",
                                           group="g2")], decisions)
    by_sha = {r["sha256"]: r for r in rows}
    assert by_sha[sha]["accepted"] == "1"
    assert by_sha[sha]["reviewer"] == "local"
    assert by_sha[sha]["reviewed_at"] == "2026-10-17T10:05:00+00:00"
    assert by_sha["b" * 64]["accepted"] == ""


def test_group_split_requires_three_groups() -> None:
    rows = [
        _plain_proposal(f"{i:064x}", f"2026-10-16T{10 + i:02d}:00:00+00:00",
                        group=f"g{i % 2}")
        for i in range(4)
    ]
    with pytest.raises(ValueError, match=">= 3 distinct group keys"):
        assign_splits(copy.deepcopy(rows), strategy="group")


def test_group_split_assigns_whole_groups() -> None:
    props = [
        _plain_proposal(f"{i:064x}", f"2026-10-16T{10 + i:02d}:00:00+00:00",
                        group=f"g{i % 3}")
        for i in range(6)
    ]
    rows = assign_splits(copy.deepcopy(props), strategy="group")
    for g in ("g0", "g1", "g2"):
        splits = {r["split"] for r in rows if r["group_key"] == g}
        assert len(splits) == 1
    group_sizes = [sum(1 for r in rows if r["group_key"] == g)
                   for g in ("g0", "g1", "g2")]
    assert sorted(group_sizes, reverse=True) == [2, 2, 2]


def test_write_manifest_csv_roundtrip(tmp_path: Path) -> None:
    rows = build_manifest([_plain_proposal("a" * 64, "2026-10-16T10:00:00+00:00")], {})
    path = tmp_path / "deep" / "manifest.csv"
    assert write_manifest_csv(rows, path) == path
    text = path.read_text(encoding="utf-8")
    first_line = text.splitlines()[0]
    assert first_line == ",".join(MANIFEST_COLUMNS)
    assert text.count("\n") == len(rows) + 1
