"""Unit tests for the metrics + aggregation module (Stage 05)."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from plantvision.vision.metrics import (
    FrameMeasurement,
    FrameRef,
    load_frames,
    load_pipeline_config,
    measure_frame,
    measure_frames,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _cfg():
    """Load the repo's real pipeline config."""
    return load_pipeline_config(REPO_ROOT / "configs" / "pipeline.yaml")


def _synthetic(with_marker: bool) -> np.ndarray:
    """400x400 white canvas with a green circle (r=40) and optional 200 px marker."""
    canvas = np.full((400, 400, 3), 255, np.uint8)
    cv2.circle(canvas, (250, 250), 40, (0, 200, 0), -1)
    if with_marker:
        m = cv2.aruco.generateImageMarker(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50), 1, 200
        )
        canvas[10:210, 10:210] = cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)
    return canvas


def _write_real_frame(folder: Path, name: str, captured_at: str, with_marker: bool) -> None:
    """Write a decodable synthetic frame jpg plus its JSON sidecar."""
    cv2.imwrite(str(folder / f"{name}.jpg"), _synthetic(with_marker))
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


def test_load_pipeline_config_defaults() -> None:
    """The repo pipeline.yaml maps onto the dataclasses with plan defaults."""
    cfg = _cfg()
    assert cfg.roi is None
    assert cfg.segmentation.method == "hsv"
    assert cfg.segmentation.open_ksize == 5
    assert cfg.quality.blur_lapvar_min == 10.0
    assert cfg.scale.aruco_dict == "DICT_5X5_50"
    assert cfg.scale.marker_size_mm == 45.0
    assert cfg.pipeline_version == "baseline-0.1"


def test_measure_frame_synthetic_with_marker() -> None:
    """A marker + green circle frame yields consistent px and cm2 metrics."""
    meas, mask = measure_frame(_synthetic(True), _cfg())
    assert meas.px_per_mm is not None
    assert meas.projected_area_px == pytest.approx(np.pi * 40**2, rel=0.15)
    assert meas.projected_area_cm2 == pytest.approx(
        meas.projected_area_px / meas.px_per_mm**2 / 100.0, rel=1e-6
    )
    assert meas.roi_fraction_pct == pytest.approx(
        100.0 * meas.projected_area_px / 160000, rel=1e-6
    )
    assert meas.bbox_w > 0 and meas.bbox_h > 0
    assert mask.shape == (400, 400)
    assert mask.dtype == np.uint8


def test_measure_frame_no_marker_none_scale() -> None:
    """Without a marker, cm-scale fields are None while px metrics stay populated."""
    meas, _ = measure_frame(_synthetic(False), _cfg())
    assert meas.px_per_mm is None
    assert meas.projected_area_cm2 is None
    assert meas.bbox_w_cm is None
    assert meas.projected_area_px > 0


def test_measure_frame_empty_mask() -> None:
    """A plant-less gray frame yields zero area, zero bbox, zero fraction."""
    img = np.full((120, 120, 3), 128, np.uint8)
    meas, _ = measure_frame(img, _cfg())
    assert meas.projected_area_px == 0
    assert meas.bbox_w == 0
    assert meas.bbox_h == 0
    assert meas.roi_fraction_pct == 0.0


def test_load_frames_pairs_sidecar(tmp_path: Path) -> None:
    """Frames without a JSON sidecar are skipped; paired frames keep captured_at."""
    (tmp_path / "a.jpg").write_bytes(b"stub")
    (tmp_path / "a.json").write_text(
        json.dumps({"captured_at": "2026-10-16T10:00:00Z"}), encoding="utf-8"
    )
    (tmp_path / "orphan.jpg").write_bytes(b"stub")
    refs = load_frames(tmp_path)
    assert len(refs) == 1
    assert refs[0].captured_at == "2026-10-16T10:00:00Z"


def test_measure_frames_aligned(tmp_path: Path) -> None:
    """measure_frames returns aligned (FrameRef, FrameMeasurement, mask) triples."""
    _write_real_frame(tmp_path, "f_a", "2026-10-16T10:00:00Z", with_marker=True)
    _write_real_frame(tmp_path, "f_b", "2026-10-16T10:01:00Z", with_marker=False)
    items = measure_frames(load_frames(tmp_path), _cfg())
    assert len(items) == 2
    for ref, meas, mask in items:
        assert isinstance(ref, FrameRef)
        assert isinstance(meas, FrameMeasurement)
        assert isinstance(mask, np.ndarray)
