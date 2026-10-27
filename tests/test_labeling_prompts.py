"""Box-prompt priors for SAM2 (plan P1.1)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import cv2
import numpy as np
import pytest

from plantvision.labeling.prompts import full_frame_box, prior_box, roi_box


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


def test_prior_box_classical_matches_roi_box() -> None:
    """Default strategy keeps the frozen HSV behaviour and labels it ``hsv``."""
    img = _image_with_mask()
    box, source = prior_box(img, strategy="classical")
    assert source == "hsv"
    assert box == roi_box(img, expand=0.15)


def test_prior_box_classical_falls_back_to_full_frame() -> None:
    """No classical mask -> full frame, honestly labelled ``full_frame``."""
    img = np.zeros((50, 80, 3), dtype=np.uint8)
    assert prior_box(img, strategy="classical") == ((0, 0, 79, 49), "full_frame")
    assert prior_box(img, strategy="full") == ((0, 0, 79, 49), "full_frame")


def test_prior_box_rejects_unknown_strategy() -> None:
    img = np.zeros((10, 20, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="strategy"):
        prior_box(img, strategy="bogus")


def test_prior_box_rejects_non_bgr_input_for_every_strategy() -> None:
    gray = np.zeros((10, 20), dtype=np.uint8)
    for strategy in ("classical", "full", "manual", "ridge", "marker"):
        with pytest.raises(ValueError, match="3-channel|shape"):
            prior_box(gray, strategy=strategy, box=(0, 0, 5, 5))


# --- manual strategy -----------------------------------------------------


def test_prior_box_manual_uses_supplied_box() -> None:
    img = np.zeros((80, 100, 3), dtype=np.uint8)
    box, source = prior_box(img, strategy="manual", box=(10, 20, 49, 69))
    assert source == "manual"
    assert box == (10, 20, 49, 69)


def test_prior_box_manual_clips_to_frame() -> None:
    img = np.zeros((80, 100, 3), dtype=np.uint8)
    box, source = prior_box(img, strategy="manual", box=(-10, -5, 150, 200))
    assert source == "manual"
    assert box == (0, 0, 99, 79)


def test_prior_box_manual_requires_a_box() -> None:
    img = np.zeros((80, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="box"):
        prior_box(img, strategy="manual")


def test_prior_box_manual_rejects_inverted_box() -> None:
    img = np.zeros((80, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="x1|x2|y1|y2|order"):
        prior_box(img, strategy="manual", box=(50, 20, 40, 30))


def test_prior_box_manual_rejects_malformed_box() -> None:
    img = np.zeros((80, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="four|box"):
        prior_box(img, strategy="manual", box=(1, 2, 3))
    with pytest.raises(ValueError, match="four|integer|box"):
        prior_box(img, strategy="manual", box=(1.5, 2, 3, 4))


def test_prior_box_manual_rejects_box_outside_frame() -> None:
    img = np.zeros((80, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="outside|frame"):
        prior_box(img, strategy="manual", box=(200, 200, 300, 300))


# --- ridge strategy ------------------------------------------------------


def _blurple_texture_image(
    shape: tuple[int, int] = (120, 160),
    rect: tuple[int, int, int, int] = (40, 30, 119, 89),
    seed: int = 7,
) -> np.ndarray:
    """Flat bright frame with a noise-textured patch that has zero green.

    Mimics basil under BLURPLE: all structure lives in blue/red, the green
    channel is identically zero, so no green-channel prior can find it.
    """
    img = np.full((shape[0], shape[1], 3), 200, dtype=np.uint8)
    x1, y1, x2, y2 = rect
    rng = np.random.default_rng(seed)
    patch_shape = (y2 - y1 + 1, x2 - x1 + 1)
    patch = np.zeros((*patch_shape, 3), dtype=np.uint8)
    patch[..., 0] = rng.integers(0, 256, patch_shape, dtype=np.uint8)
    patch[..., 2] = rng.integers(0, 256, patch_shape, dtype=np.uint8)
    img[y1 : y2 + 1, x1 : x2 + 1] = patch
    return img


def test_prior_box_ridge_finds_textured_blurple_patch() -> None:
    """Texture in B/R only (G == 0) still yields a tight ``ridge`` box."""
    img = _blurple_texture_image()
    box, source = prior_box(img, strategy="ridge")
    assert source == "ridge"
    x1, y1, x2, y2 = box
    # The box brackets the patch and is nowhere near full frame.
    assert x1 <= 40 and y1 <= 30 and x2 >= 119 and y2 >= 89
    assert x1 > 0 and y1 > 0 and x2 < 159 and y2 < 119


def test_prior_box_ridge_falls_back_on_flat_frame() -> None:
    img = np.full((60, 80, 3), 128, dtype=np.uint8)
    assert prior_box(img, strategy="ridge") == ((0, 0, 79, 59), "full_frame")


def test_prior_box_ridge_rejects_bad_expand() -> None:
    img = _blurple_texture_image()
    with pytest.raises(ValueError, match="expand"):
        prior_box(img, strategy="ridge", expand=1.5)


# --- marker strategy -----------------------------------------------------


def _image_with_aruco(
    shape: tuple[int, int] = (480, 640),
    origin: tuple[int, int] = (200, 100),
    marker_px: int = 120,
    marker_id: int = 2,
) -> np.ndarray:
    """Paste a synthetic ``DICT_5X5_50`` marker into a flat BGR canvas.

    Args:
        shape: Canvas ``(H, W)``.
        origin: Top-left pixel ``(x, y)`` of the pasted marker.
        marker_px: Marker side in pixels.
        marker_id: ArUco marker id to render.

    Returns:
        BGR uint8 canvas with the marker pasted at ``origin``.
    """
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50)
    marker = cv2.aruco.generateImageMarker(dictionary, marker_id, marker_px)
    img = np.full((shape[0], shape[1], 3), 128, dtype=np.uint8)
    x, y = origin
    img[y : y + marker_px, x : x + marker_px] = cv2.cvtColor(
        marker, cv2.COLOR_GRAY2BGR
    )
    return img


def test_prior_box_marker_places_box_above_marker() -> None:
    """Synthetic ArUco marker -> ``marker`` box above it, clipped to frame."""
    img = _image_with_aruco()
    box, source = prior_box(img, strategy="marker")
    assert source == "marker"
    x1, y1, x2, y2 = box
    assert all(isinstance(v, int) for v in box)
    # Box spans the marker horizontally and sits above the marker centre.
    assert x1 < 200 and x2 > 320
    assert y1 < 100
    assert y2 < 100 + 60
    assert 0 <= x1 <= x2 < 640 and 0 <= y1 <= y2 < 480


def test_prior_box_marker_clips_at_frame_border() -> None:
    """A marker near the top-left edge yields a frame-clipped box."""
    img = _image_with_aruco(origin=(20, 10))
    box, source = prior_box(img, strategy="marker")
    assert source == "marker"
    x1, y1, x2, y2 = box
    assert x1 == 0 and y1 == 0
    assert 0 <= x2 < 640 and 0 <= y2 < 480


def test_prior_box_marker_falls_back_without_marker() -> None:
    """No ArUco marker -> full frame, honestly labelled ``full_frame``."""
    img = np.full((60, 80, 3), 128, dtype=np.uint8)
    assert prior_box(img, strategy="marker") == ((0, 0, 79, 59), "full_frame")


def test_prior_box_cli_accepts_marker_strategy() -> None:
    """``--box-strategy marker`` is a valid CLI choice."""
    parse_args = _load_label_script().parse_args
    assert parse_args(["--box-strategy", "marker"]).box_strategy == "marker"


def _load_label_script():
    """Load ``scripts/label_sam2.py`` without package machinery."""
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "label_sam2", root / "scripts" / "label_sam2.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_prior_box_cli_box_parser_round_trip() -> None:
    """The CLI parser accepts only a four-integer comma-separated box."""
    import argparse

    parse_box = _load_label_script()._parse_box
    assert parse_box("1,2,3,4") == (1, 2, 3, 4)
    with pytest.raises(argparse.ArgumentTypeError):
        parse_box("1,2,3")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_box("a,b,c,d")
