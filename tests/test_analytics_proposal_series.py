"""Tests for the torch-free proposals -> canonical rows analytics node."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from plantvision.analytics.proposal_series import (
    Proposal,
    build_rows,
    read_proposals,
)
from plantvision.analytics.timeseries import TIMESERIES_COLUMNS

_ROOT = Path(__file__).resolve().parents[1]
_SHA = "a" * 64
_TS = "2026-10-24T05:48:26.000000Z"


def _marker_frame() -> np.ndarray:
    """400x400 white BGR frame with a 100 px ArUco marker (id 2)."""
    frame = np.full((400, 400, 3), 255, dtype=np.uint8)
    marker = cv2.aruco.generateImageMarker(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50), 2, 100
    )
    frame[50:150, 50:150] = marker[..., None]
    return frame


def _plain_frame() -> np.ndarray:
    """400x400 white BGR frame without any marker."""
    return np.full((400, 400, 3), 255, dtype=np.uint8)


def _mask() -> np.ndarray:
    """400x400 mask with exactly 10100 foreground pixels."""
    mask = np.zeros((400, 400), dtype=np.uint8)
    mask[150:251, 200:300] = 255
    return mask


def _empty_mask() -> np.ndarray:
    """400x400 mask with no foreground pixel."""
    return np.zeros((400, 400), dtype=np.uint8)


def _sidecar(sha: str, ts: str, *, camera: str = "farm-02", zone: str = "farm/zone-b") -> dict:
    """Minimal sidecar matching the capture store shape."""
    return {
        "sha256": sha,
        "captured_at": ts,
        "camera_id": camera,
        "zone_id": zone,
        "width": 400,
        "height": 400,
        "received_at": ts,
        "quality_flags": ["red"],
        "brightness": 112.0,
        "blur_lapvar": 900.0,
    }


def _proposal(
    sha: str,
    ts: str = _TS,
    *,
    relpath: str = "farm_zone-b/2026-10-24/f.jpg",
    box_source: str = "marker",
) -> dict:
    """Proposal JSON line payload."""
    return {
        "sha256": sha,
        "captured_at": ts,
        "frame_relpath": relpath,
        "mask_relpath": f"masks/{sha}.png",
        "area_fraction": 0.063125,
        "box_source": box_source,
        "width": 400,
        "height": 400,
        "score": 0.91,
    }


def _write_case(
    tmp_path: Path,
    sha: str = _SHA,
    *,
    frame: np.ndarray | None = None,
    mask: np.ndarray | None = None,
    relpath: str = "farm_zone-b/2026-10-24/f.jpg",
    ts: str = _TS,
) -> tuple[Path, Path]:
    """Write one originals frame + sidecar and one mask; return both roots."""
    originals = tmp_path / "originals"
    labels = tmp_path / "labels"
    frame_path = originals / relpath
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    if frame is not None:
        cv2.imwrite(str(frame_path), frame)
    sidecar = frame_path.with_suffix(".json")
    sidecar.write_text(json.dumps(_sidecar(sha, ts)), encoding="utf-8")
    mask_path = labels / f"masks/{sha}.png"
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    if mask is not None:
        cv2.imwrite(str(mask_path), mask)
    return originals, labels


def _build(tmp_path: Path, review: dict[str, str], **kwargs):
    """Build one row for the standard fixture."""
    relpath = kwargs.pop("relpath", "farm_zone-b/2026-10-24/f.jpg")
    originals, labels = _write_case(
        tmp_path,
        frame=_marker_frame() if kwargs.pop("marker", True) else _plain_frame(),
        mask=_mask(),
        relpath=relpath,
    )
    proposal = Proposal(
        sha256=_SHA,
        captured_at=_TS,
        frame_relpath=relpath,
        mask_relpath=f"masks/{_SHA}.png",
        box_source="marker",
        width=400,
        height=400,
    )
    kwargs.setdefault("biosource_id", "basil")
    return build_rows(
        [proposal],
        review,
        originals_root=originals,
        labels_root=labels,
        **kwargs,
    )


def _write_proposals(path: Path, rows: list[dict]) -> None:
    """Write JSONL proposals."""
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def test_read_proposals_parses_valid_file(tmp_path: Path) -> None:
    path = tmp_path / "proposals.jsonl"
    first = _proposal(_SHA)
    second = _proposal("b" * 64, ts="2026-10-24T05:53:26.000000Z")
    _write_proposals(path, [first, second])
    proposals = read_proposals(path)
    assert [p.sha256 for p in proposals] == [_SHA, "b" * 64]
    assert proposals[0].captured_at == _TS
    assert proposals[0].frame_relpath == first["frame_relpath"]
    assert proposals[0].mask_relpath == first["mask_relpath"]
    assert proposals[0].box_source == "marker"
    assert proposals[0].width == 400
    assert proposals[0].height == 400


def test_read_proposals_rejects_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "proposals.jsonl"
    payload = _proposal(_SHA)
    payload.pop("mask_relpath")
    _write_proposals(path, [payload])
    with pytest.raises(ValueError, match=r"line 1.*mask_relpath"):
        read_proposals(path)


def test_read_proposals_rejects_duplicate_sha(tmp_path: Path) -> None:
    path = tmp_path / "proposals.jsonl"
    _write_proposals(path, [_proposal(_SHA), _proposal(_SHA)])
    with pytest.raises(ValueError, match=_SHA):
        read_proposals(path)


def test_build_rows_maps_canonical_columns(tmp_path: Path) -> None:
    result = _build(tmp_path, {_SHA: "1"})
    assert len(result.rows) == 1
    row = result.rows[0]
    assert set(row) == set(TIMESERIES_COLUMNS)
    assert row["camera_id"] == "farm-02"
    assert row["zone_id"] == "farm-02/farm_zone-b"
    assert row["biosource_id"] == "basil"
    assert row["experiment_id"] == "farm02-sam2-v1"
    assert row["observation_unit_id"] == "farm-02/farm_zone-b"
    assert row["treatment_id"] == ""
    assert row["light_regime"] == ""
    assert row["settings_source"] == ""
    assert row["scale_ok"] == "true"
    assert row["area_px"] == "10100"
    assert row["solidity"] != ""
    assert row["hull_area_px"] != ""
    assert abs(float(row["roi_fraction_pct"]) - 6.3125) < 1e-3


def test_build_rows_excludes_rejected() -> None:
    result = build_rows(
        [Proposal(_SHA, _TS, "f.jpg", f"masks/{_SHA}.png", "marker", 400, 400)],
        {_SHA: "0"},
        originals_root="unused",
        labels_root="unused",
    )
    assert result.rows == ()
    assert result.excluded_rejected == 1


def test_review_status_accepted_excludes_pending(tmp_path: Path) -> None:
    result = _build(tmp_path, {_SHA: ""}, review_status="accepted")
    assert result.rows == ()
    assert result.excluded_review == 1


def test_pending_row_carries_label_pending_flag(tmp_path: Path) -> None:
    result = _build(tmp_path, {_SHA: ""})
    assert result.rows[0]["quality_flag"].endswith("label_pending")


def test_missing_mask_records_error_and_skips(tmp_path: Path) -> None:
    originals, labels = _write_case(tmp_path, frame=_marker_frame(), mask=None)
    proposal = Proposal(
        _SHA, _TS, "farm_zone-b/2026-10-24/f.jpg", f"masks/{_SHA}.png", "marker", 400, 400
    )
    result = build_rows([proposal], {_SHA: "1"}, originals_root=originals, labels_root=labels)
    assert result.missing_mask == 1
    assert _SHA in result.errors[0]
    assert result.rows == ()


def test_missing_frame_records_error_and_skips(tmp_path: Path) -> None:
    originals, labels = _write_case(
        tmp_path, frame=None, mask=_mask(), relpath="missing/f.jpg"
    )
    proposal = Proposal(
        _SHA, _TS, "missing/f.jpg", f"masks/{_SHA}.png", "marker", 400, 400
    )
    result = build_rows([proposal], {_SHA: "1"}, originals_root=originals, labels_root=labels)
    assert result.missing_frame == 1
    assert _SHA in result.errors[0]


def test_missing_marker_leaves_scale_blank(tmp_path: Path) -> None:
    result = _build(tmp_path, {_SHA: "1"}, marker=False)
    row = result.rows[0]
    assert row["scale_ok"] == "false"
    assert row["px_per_mm"] == ""
    assert row["area_cm2"] == ""


def test_rows_sorted_by_captured_at_then_sha(tmp_path: Path) -> None:
    originals, labels = _write_case(tmp_path, frame=_marker_frame(), mask=_mask())
    for sha in ("b" * 64, "c" * 64):
        cv2.imwrite(str(labels / "masks" / f"{sha}.png"), _mask())
    later = Proposal(
        "b" * 64, "2026-10-24T06:00:00.000000Z",
        "farm_zone-b/2026-10-24/f.jpg", "masks/" + "b" * 64 + ".png", "marker", 400, 400,
    )
    earlier = Proposal(
        "c" * 64, "2026-10-24T05:00:00.000000Z",
        "farm_zone-b/2026-10-24/f.jpg", "masks/" + "c" * 64 + ".png", "marker", 400, 400,
    )
    result = build_rows(
        [later, earlier], {}, originals_root=originals, labels_root=labels
    )
    assert [row["sha256"] for row in result.rows] == ["c" * 64, "b" * 64]


def test_proposal_series_imports_without_torch() -> None:
    code = (
        "import sys; import plantvision.analytics.proposal_series; "
        "assert 'torch' not in sys.modules"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=_ROOT, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
