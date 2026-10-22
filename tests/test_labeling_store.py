"""Mask I/O and append-only JSONL logs (plan Section 6 Step 4)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from plantvision.labeling.store import (
    append_jsonl,
    latest_decisions,
    latest_proposals,
    normalize_mask,
    read_jsonl,
    read_mask,
    write_mask,
)


def _mask_with_foreground(shape: tuple[int, int] = (6, 10)) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    mask[1:3, 2:5] = 255
    return mask


def test_mask_roundtrip_preserves_shape_and_values(tmp_path: Path) -> None:
    path = tmp_path / "masks" / "abc.png"
    mask = _mask_with_foreground()
    assert write_mask(mask, path) == path
    loaded = read_mask(path)
    assert loaded.shape == mask.shape
    assert loaded.dtype == np.uint8
    assert set(np.unique(loaded).tolist()) <= {0, 255}
    assert np.array_equal(loaded, mask)

    zero = np.zeros((6, 10), dtype=np.uint8)
    zero_path = tmp_path / "masks" / "zero.png"
    write_mask(zero, zero_path)
    assert np.array_equal(read_mask(zero_path), zero)


def test_read_mask_rejects_non_binary(tmp_path: Path) -> None:
    path = tmp_path / "grey.png"
    assert __import__("cv2").imwrite(str(path), np.zeros((6, 10), np.uint8) + 7)
    with pytest.raises(ValueError, match="not binary"):
        read_mask(path)
    with pytest.raises(RuntimeError, match="cannot read mask"):
        read_mask(tmp_path / "missing.png")


def test_normalize_mask_from_bool_and_float() -> None:
    bool_mask = np.array([[True, False], [False, False]], dtype=bool)
    assert np.array_equal(
        normalize_mask(bool_mask), np.array([[255, 0], [0, 0]], dtype=np.uint8)
    )
    float_mask = np.array([[0.0, 1.0], [0.5, 0.0]], dtype=np.float64)
    assert np.array_equal(
        normalize_mask(float_mask), np.array([[0, 255], [255, 0]], dtype=np.uint8)
    )
    stacked = np.dstack([np.ones((2, 2)), np.ones((2, 2)), np.ones((2, 2))]
                        ).astype(np.uint8) * np.uint8(77)
    assert normalize_mask(stacked).shape == (2, 2)
    with pytest.raises(ValueError, match="2-D"):
        normalize_mask(np.zeros((2, 3, 4, 5), dtype=np.uint8))
    with pytest.raises(ValueError, match="2-D"):
        normalize_mask(np.zeros(4, dtype=np.uint8))


def test_append_jsonl_appends_without_rewriting(tmp_path: Path) -> None:
    path = tmp_path / "logs" / "proposals.jsonl"
    append_jsonl(path, {"sha256": "a" * 64, "score": 0.9})
    append_jsonl(path, {"sha256": "b" * 64, "score": 0.8})
    first_two = path.read_bytes()
    records = read_jsonl(path)
    assert [r["sha256"] for r in records] == ["a" * 64, "b" * 64]
    append_jsonl(path, {"sha256": "c" * 64, "score": 0.7})
    assert path.read_bytes()[: len(first_two)] == first_two
    assert [r["sha256"] for r in read_jsonl(path)] == [
        "a" * 64,
        "b" * 64,
        "c" * 64,
    ]
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_latest_proposals_last_line_wins() -> None:
    records = [
        {"sha256": "a" * 64, "score": 0.1, "box": [1, 1, 2, 2]},
        {"sha256": "b" * 64, "score": 0.2, "box": [3, 3, 4, 4]},
        {"sha256": "a" * 64, "score": 0.9, "box": [5, 5, 6, 6]},
    ]
    latest = latest_proposals(records)
    assert set(latest) == {"a" * 64, "b" * 64}
    assert latest["a" * 64]["score"] == 0.9
    assert latest["b" * 64]["box"] == [3, 3, 4, 4]


def test_latest_decisions_last_line_wins() -> None:
    records = [
        {"sha256": "a" * 64, "verdict": "reject", "reason": "not_a_plant"},
        {"sha256": "a" * 64, "verdict": "accept", "reason": ""},
    ]
    latest = latest_decisions(records)
    assert len(latest) == 1
    assert latest["a" * 64]["verdict"] == "accept"
    assert latest["a" * 64]["reason"] == ""


def test_read_jsonl_missing_file_and_blank_lines(tmp_path: Path) -> None:
    assert read_jsonl(tmp_path / "nope.jsonl") == []
    path = tmp_path / "x.jsonl"
    path.write_text(
        json.dumps({"sha256": "a" * 64}) + "\n\n"
        + json.dumps({"sha256": "b" * 64}) + "\n\n",
        encoding="utf-8",
    )
    assert [r["sha256"] for r in read_jsonl(path)] == ["a" * 64, "b" * 64]
