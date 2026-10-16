"""Unit tests for the classic plant segmentation module (Stage 05)."""

import cv2
import numpy as np
import pytest

from plantvision.vision.segmentation import (
    clean_mask,
    exg_mask,
    green_mask_hsv,
    largest_component,
    segment_plant,
)


def _gray_canvas_with_green_circle() -> np.ndarray:
    """Build a gray (128, 128, 128) canvas with a filled green circle at center."""
    img = np.full((120, 120, 3), 128, np.uint8)
    cv2.circle(img, (60, 60), 20, (0, 200, 0), -1)
    return img


def test_hsv_mask_green_blob() -> None:
    """HSV band (25,40,40)-(95,255,255) captures a saturated green circle."""
    img = _gray_canvas_with_green_circle()
    assert cv2.countNonZero(green_mask_hsv(img)) >= 1100


def test_exg_mask_green_vs_gray() -> None:
    """ExG separates green pixels from neutral gray (2G-R-B == 0 for gray)."""
    img = _gray_canvas_with_green_circle()
    assert cv2.countNonZero(exg_mask(img)) >= 1100
    gray_img = np.full((120, 120, 3), 128, np.uint8)
    assert cv2.countNonZero(exg_mask(gray_img)) == 0


def test_clean_mask_removes_specks() -> None:
    """Morphological open removes an isolated speck but keeps the solid block.

    MORPH_ELLIPSE opening trims the block corners, so an exact 400 px count is
    geometrically impossible; assert intent (speck gone, block within band).
    """
    y0, x0 = 40, 40
    mask = np.zeros((120, 120), np.uint8)
    mask[y0:y0 + 20, x0:x0 + 20] = 255
    mask[y0 - 2, x0 - 2] = 255
    cleaned = clean_mask(mask, open_ksize=5, close_ksize=1)
    assert cleaned[y0 - 2, x0 - 2] == 0
    assert 380 <= cv2.countNonZero(cleaned) <= 400


def test_largest_component_picks_biggest() -> None:
    """Largest connected component keeps the 400 px block, drops the 100 px one."""
    mask = np.zeros((120, 120), np.uint8)
    mask[10:20, 10:20] = 255
    mask[50:70, 50:70] = 255
    assert cv2.countNonZero(largest_component(mask)) == 400


def test_no_green_returns_empty() -> None:
    """A plant-less gray frame yields an all-zero segmentation."""
    img = np.full((120, 120, 3), 128, np.uint8)
    assert cv2.countNonZero(segment_plant(img)) == 0


def test_segment_plant_bad_method_raises() -> None:
    """Unknown method name raises ValueError (never returns None)."""
    img = np.full((120, 120, 3), 128, np.uint8)
    with pytest.raises(ValueError):
        segment_plant(img, method="nope")
