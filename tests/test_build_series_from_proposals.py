"""CLI tests for scripts/build_series_from_proposals.py (importlib load)."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from plantvision.analytics.timeseries import TIMESERIES_COLUMNS

_ROOT = Path(__file__).resolve().parents[1]
_SHA = "a" * 64
_TS = "2026-10-24T05:48:26.000000Z"


def _load_cli():
    """Load scripts/build_series_from_proposals.py without package machinery."""
    spec = importlib.util.spec_from_file_location(
        "build_series_from_proposals",
        _ROOT / "scripts" / "build_series_from_proposals.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _marker_frame() -> np.ndarray:
    """400x400 white BGR frame with a 100 px ArUco marker."""
    frame = np.full((400, 400, 3), 255, dtype=np.uint8)
    marker = cv2.aruco.generateImageMarker(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50), 2, 100
    )
    frame[50:150, 50:150] = marker[..., None]
    return frame


def _write_case(tmp_path: Path, accepted: str = "1") -> dict[str, str]:
    """Write proposals, manifest, one frame+sidecar and one mask."""
    proposals = tmp_path / "proposals.jsonl"
    proposals.write_text(json.dumps({
        "sha256": _SHA,
        "captured_at": _TS,
        "frame_relpath": "farm_zone-b/2026-10-24/f.jpg",
        "mask_relpath": f"masks/{_SHA}.png",
        "area_fraction": 0.063125,
        "box_source": "marker",
        "width": 400,
        "height": 400,
        "score": 0.91,
    }) + "\n", encoding="utf-8")

    manifest = tmp_path / "manifest.csv"
    manifest.write_text(f"sha256,accepted\n{_SHA},{accepted}\n", encoding="utf-8")

    originals = tmp_path / "originals"
    frame_path = originals / "farm_zone-b/2026-10-24/f.jpg"
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(frame_path), _marker_frame())
    frame_path.with_suffix(".json").write_text(json.dumps({
        "sha256": _SHA,
        "captured_at": _TS,
        "camera_id": "farm-02",
        "zone_id": "farm/zone-b",
        "width": 400,
        "height": 400,
        "received_at": _TS,
        "quality_flags": ["red"],
        "brightness": 112.0,
        "blur_lapvar": 900.0,
    }), encoding="utf-8")

    labels = tmp_path / "labels"
    mask_path = labels / "masks" / f"{_SHA}.png"
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    mask = np.zeros((400, 400), dtype=np.uint8)
    mask[150:251, 200:300] = 255
    cv2.imwrite(str(mask_path), mask)

    return {
        "proposals": str(proposals),
        "manifest": str(manifest),
        "originals": str(originals),
        "labels": str(labels),
        "config": str(_ROOT / "configs" / "pipeline.yaml"),
    }


def _argv(paths: dict[str, str], out: Path, *extra: str) -> list[str]:
    """Full CLI argv for one fixture."""
    return [
        "--proposals", paths["proposals"],
        "--manifest", paths["manifest"],
        "--originals", paths["originals"],
        "--labels", paths["labels"],
        "--config", paths["config"],
        "--out", str(out),
        *extra,
    ]


def _payload(capsys) -> dict:
    """Parse the single JSON line printed by the CLI."""
    captured = capsys.readouterr()
    return json.loads(captured.out.strip().splitlines()[-1])


def test_main_writes_csv_and_prints_ok_json(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    paths = _write_case(tmp_path)
    out = tmp_path / "out.csv"
    assert cli.main(_argv(paths, out)) == 0
    payload = _payload(capsys)
    assert payload["status"] == "ok"
    assert payload["rows"] == 1
    with out.open(newline="", encoding="utf-8") as handle:
        header = tuple(next(csv.reader(handle)))
    assert header == TIMESERIES_COLUMNS


def test_main_missing_proposals_exits_1(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    paths = _write_case(tmp_path)
    paths["proposals"] = str(tmp_path / "absent.jsonl")
    assert cli.main(_argv(paths, tmp_path / "out.csv")) == 1
    payload = _payload(capsys)
    assert payload["status"] == "error"
    assert "absent.jsonl" in payload["error"]


def test_main_no_rows_exits_1(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    paths = _write_case(tmp_path, accepted="0")
    assert cli.main(_argv(paths, tmp_path / "out.csv")) == 1
    payload = _payload(capsys)
    assert payload["status"] == "error"
    assert "no rows selected" in payload["error"]


def test_main_bad_review_status_exits_2(tmp_path: Path) -> None:
    cli = _load_cli()
    paths = _write_case(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        cli.main(_argv(paths, tmp_path / "out.csv", "--review-status", "bogus"))
    assert excinfo.value.code == 2


def test_main_output_is_byte_identical_across_runs(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    paths = _write_case(tmp_path)
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    assert cli.main(_argv(paths, first)) == 0
    assert cli.main(_argv(paths, second)) == 0
    _payload(capsys)
    assert first.read_bytes() == second.read_bytes()
