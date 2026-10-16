"""Unit tests for the per-frame ArUco scale module (Stage 05)."""

import cv2
import numpy as np
import pytest

from plantvision.vision.scale import detect_markers, marker_side_px, px_per_mm


def _marker_canvas() -> np.ndarray:
    """White 400x400 grayscale canvas with a 200 px id=1 DICT_5X5_50 marker."""
    canvas = np.full((400, 400), 255, np.uint8)
    canvas[100:300, 100:300] = cv2.aruco.generateImageMarker(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50), 1, 200
    )
    return canvas


def test_px_per_mm_detects_marker() -> None:
    """A 200 px marker on a 45 mm reference gives px/mm close to 200/45."""
    r = px_per_mm(_marker_canvas(), 45.0)
    assert r is not None
    assert r == pytest.approx(200 / 45, rel=0.05)


def test_detect_markers_returns_id_and_corners() -> None:
    """Detection returns the marker id and its (4, 2) corner array."""
    markers = detect_markers(_marker_canvas())
    assert len(markers) == 1
    assert markers[0]["id"] == 1
    assert markers[0]["corners"].shape == (4, 2)


def test_px_per_mm_no_marker_returns_none() -> None:
    """A frame without a marker yields None (F1), never a fabricated number."""
    plain = np.full((400, 400, 3), 255, np.uint8)
    assert px_per_mm(plain) is None


def test_marker_side_px_square() -> None:
    """Axis-aligned 100 px square corners give a mean side of 100."""
    corners = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], float)
    assert marker_side_px(corners) == pytest.approx(100.0)


def test_unknown_dict_raises() -> None:
    """An unknown dictionary name raises ValueError."""
    with pytest.raises(ValueError):
        px_per_mm(_marker_canvas(), dict_name="NOT_A_DICT")


def test_marker_size_nonpositive_raises() -> None:
    """A non-positive marker size raises ValueError."""
    with pytest.raises(ValueError):
        px_per_mm(_marker_canvas(), 0.0)
