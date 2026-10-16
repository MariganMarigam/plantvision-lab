"""Integration test: scripts/measure_series.py end-to-end on synthetic frames."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np


def _load_script():
    """Load scripts/measure_series.py as a module without package machinery."""
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "measure_series", root / "scripts" / "measure_series.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_frame(folder: Path, name: str, captured_at: str, with_marker: bool) -> None:
    """Write one 400x400 synthetic frame (green circle, optional marker) + sidecar."""
    folder.mkdir(parents=True, exist_ok=True)
    canvas = np.full((400, 400, 3), 255, np.uint8)
    cv2.circle(canvas, (250, 250), 40, (0, 200, 0), -1)
    if with_marker:
        m = cv2.aruco.generateImageMarker(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50), 1, 200
        )
        canvas[10:210, 10:210] = cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)
    cv2.imwrite(str(folder / f"{name}.jpg"), canvas)
    sidecar = {
        "sha256": name[:16].ljust(16, "0"),
        "captured_at": captured_at,
        "camera_id": "cam-a",
        "zone_id": "z",
        "width": 400,
        "height": 400,
        "byte_size": 1,
        "quality": "ok",
        "received_at": captured_at,
    }
    (folder / f"{name}.json").write_text(json.dumps(sidecar), encoding="utf-8")


def test_measure_series_writes_outputs(tmp_path: Path) -> None:
    """The script writes CSV (F1 cell empty), plot PNG, summary, and 1:1 masks."""
    orig = tmp_path / "originals" / "cam-a" / "z" / "2026-10-16"
    _write_frame(orig, "frame_a", "2026-10-16T10:00:00Z", with_marker=True)
    _write_frame(orig, "frame_b", "2026-10-16T10:01:00Z", with_marker=False)
    mod = _load_script()
    root = Path(__file__).resolve().parent.parent
    rc = mod.main(
        [
            "--originals", str(orig.parent.parent.parent),
            "--config", str(root / "configs" / "pipeline.yaml"),
            "--masks", str(tmp_path / "masks"),
            "--out", str(tmp_path / "out"),
            "--zone", "z",
        ]
    )
    assert rc == 0
    csv_path = tmp_path / "out" / "projected-area-z.csv"
    assert csv_path.exists()
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert any(r["projected_area_cm2"] != "" for r in rows)
    assert any(r["projected_area_cm2"] == "" for r in rows)
    png = tmp_path / "out" / "projected-area-z.png"
    assert png.exists()
    assert cv2.imread(str(png)) is not None
    summary = tmp_path / "out" / "run_summary.md"
    assert summary.exists()
    txt = summary.read_text(encoding="utf-8")
    assert "no scale" in txt.lower()
    masks = list((tmp_path / "masks").rglob("*.png"))
    assert len(masks) == 2
