"""Classical ROI box prior for SAM2 (plan Section 6 Step 3)."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from plantvision.labeling.prompts import full_frame_box, roi_box


def _image_with_mask(
    shape: tuple[int, int] = (100, 100),
    rect: tuple[int, int, int, int] = (30, 20, 69, 49),
    color: tuple[int, int, int] = (0, 255, 0),
) -> np.ndarray:
    """A black BGR frame with a solid green rectangle (inclusive corners)."""
    img = np.zeros((shape[0], shape[1], 3), dtype=np.uint8)
    x1, y1, x2, y2 = rect
    img[y1 : y2 + 1, x1 : x2 + 1] = color
    return img


def test_roi_box_covers_blob_with_expansion() -> None:
    """Tight bbox (30,20)-(69,49) expanded by 15% and clipped inside frame."""
    img = _image_with_mask()
    box = roi_box(img, expand=0.15)
    assert box is not None
    x1, y1, x2, y2 = box
    w, h = 40, 30
    dx, dy = int(round(w * 0.15)), int(round(h * 0.15))
    assert box == (30 - dx, 20 - dy, 69 + dx, 49 + dy)
    assert x1 <= 30 and y1 <= 20 and x2 >= 69 and y2 >= 49
    assert all(isinstance(v, int) for v in box)


def test_roi_box_returns_none_for_empty_image() -> None:
    assert roi_box(np.zeros((50, 80, 3), dtype=np.uint8)) is None


def test_roi_box_clips_at_frame_border() -> None:
    """Blob touching left/top edge keeps x1/y1 at 0 after expansion."""
    img = _image_with_mask(rect=(0, 0, 19, 19))
    box = roi_box(img, expand=0.15)
    assert box is not None
    w = h = 20
    dx = dy = int(round(w * 0.15))
    assert box == (0, 0, 19 + dx, 19 + dy)


def test_roi_box_rejects_non_bgr_input() -> None:
    gray = np.zeros((10, 20), dtype=np.uint8)
    with pytest.raises(ValueError, match="3-channel|shape"):
        roi_box(gray)


def test_full_frame_box_is_frame_inset_by_zero() -> None:
    assert full_frame_box(np.zeros((10, 20, 3), dtype=np.uint8)) == (0, 0, 19, 9)


def test_roi_box_rejects_bad_expand() -> None:
    img = _image_with_mask()
    with pytest.raises(ValueError):
        roi_box(img, expand=1.5)
    with pytest.raises(ValueError):
        roi_box(img, expand=-0.1)
