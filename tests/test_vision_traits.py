"""Unit tests for shape traits and their time-series row (P1.5.1)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from plantvision.analytics.timeseries import FrameRecord, format_row
from plantvision.vision.metrics import FrameMeasurement
from plantvision.vision.traits import ShapeTraits, compute_traits

_TRAIT_COLUMNS = (
    "solidity", "hull_area_px", "hull_area_cm2", "perimeter_px", "perimeter_cm",
    "ellipse_major_px", "ellipse_minor_px", "extent", "n_components",
)


def _filled_square(size: int = 100) -> np.ndarray:
    """A filled ``size`` x ``size`` square inside a 120 x 120 canvas."""
    mask = np.zeros((size + 20, size + 20), np.uint8)
    mask[10:10 + size, 10:10 + size] = 255
    return mask


def _measurement(**overrides: object) -> FrameMeasurement:
    """A minimal FrameMeasurement with per-test overrides."""
    fields: dict[str, object] = {
        "stem": "frame_a",
        "captured_at": "2026-10-16T10:00:00Z",
        "px_per_mm": 5.0,
        "projected_area_px": 10000,
        "projected_area_cm2": 4.0,
        "roi_fraction_pct": 10.0,
        "bbox_w": 100,
        "bbox_h": 100,
        "bbox_w_cm": 2.0,
        "bbox_h_cm": 2.0,
        "blur_lapvar": 16.0,
        "brightness_mean": 128.0,
        "quality_flags": (),
    }
    fields.update(overrides)
    return FrameMeasurement(**fields)


def _record(tmp_path: Path) -> FrameRecord:
    """A FrameRecord with a synthetic path and no provenance."""
    return FrameRecord(
        jpg=tmp_path / "frame_a.jpg",
        sha256="a" * 64,
        captured_at="2026-10-16T10:00:00Z",
        received_at="2026-10-16T10:00:01Z",
        camera_id="cam-a",
        zone_id="z",
        width=400,
        height=400,
    )


def test_filled_square_geometry() -> None:
    """A filled square is fully solid; contour geometry follows OpenCV pixel centres.

    OpenCV traces pixel centres, so a 100-pixel-wide square has a 99-pixel-wide
    contour: contour area 9801 and perimeter 396. The shape is still one solid
    component with equal ellipse axes.
    """
    traits = compute_traits(_filled_square())
    assert traits is not None
    assert traits.solidity == pytest.approx(1.0, abs=1e-6)
    assert traits.extent == pytest.approx(9801 / 10000, abs=1e-6)
    assert traits.perimeter_px == pytest.approx(396.0, abs=2.0)
    assert abs(traits.ellipse_major_px - traits.ellipse_minor_px) <= 1.0
    assert traits.n_components == 1
    assert traits.hull_area_px == pytest.approx(9801.0, abs=1.0)


def test_comb_has_lower_solidity_and_extent() -> None:
    """Three 20 x 40 notches collapse solidity and extent below a solid box."""
    mask = _filled_square()
    for x in (20, 50, 80):
        mask[10:50, x:x + 20] = 0
    traits = compute_traits(mask)
    assert traits is not None
    assert traits.solidity < 0.95
    assert traits.extent < 1.0


def test_all_zero_mask_returns_none_and_blank_cells(tmp_path: Path) -> None:
    """An empty mask is not measurable: None traits and nine blank CSV cells."""
    assert compute_traits(np.zeros((50, 50), np.uint8)) is None
    row = format_row(_record(tmp_path), _measurement())
    assert set(row) >= set(_TRAIT_COLUMNS)
    for column in _TRAIT_COLUMNS:
        assert row[column] == ""


def test_single_pixel_is_measured_not_dropped() -> None:
    """A degenerate one-pixel mask keeps its component count and never raises."""
    mask = np.zeros((20, 20), np.uint8)
    mask[10, 10] = 1
    traits = compute_traits(mask)
    assert traits is not None
    assert traits.n_components == 1
    assert traits.perimeter_px >= 0.0


def test_deterministic_frozen_dataclass() -> None:
    """Two calls on the same mask compare equal bit-for-bit."""
    mask = _filled_square()
    first = compute_traits(mask)
    second = compute_traits(mask)
    assert isinstance(first, ShapeTraits)
    assert first == second


def test_two_pixels_are_one_component() -> None:
    """Adjacent pixels form one 8-connected component."""
    mask = np.zeros((20, 20), np.uint8)
    mask[10, 10] = mask[10, 11] = 255
    traits = compute_traits(mask)
    assert traits is not None
    assert traits.n_components == 1
