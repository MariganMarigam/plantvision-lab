"""Tests for plantvision.vision.colors color-space helpers."""

import numpy as np
import pytest

from plantvision.vision.colors import (
    hue_histogram,
    split_channels,
    to_gray,
    to_hsv,
)


def test_to_hsv_pure_red() -> None:
    """Pure BGR red [[0,0,255]] converts to HSV with hue near 0."""
    hsv = to_hsv(np.array([[[0, 0, 255]]], dtype=np.uint8))

    assert hsv.shape == (1, 1, 3)
    assert hsv.dtype == np.uint8
    assert int(hsv[0, 0, 0]) == pytest.approx(0, abs=1)


def test_split_channels_keys() -> None:
    """split_channels returns the documented key sets per color space."""
    img = np.zeros((2, 2, 3), dtype=np.uint8)

    assert set(split_channels(img, "bgr")) == {"b", "g", "r"}
    assert set(split_channels(img, "hsv")) == {"h", "s", "v"}
    bgr = np.zeros((2, 2, 3), dtype=np.uint8)
    assert set(split_channels(bgr, "gray")) == {"gray"}


def test_hue_histogram_len() -> None:
    """hue_histogram returns hist and bin centers, both of length == bins."""
    hsv = np.zeros((4, 4, 3), dtype=np.uint8)

    hist, centers = hue_histogram(hsv, bins=36)

    assert len(hist) == 36
    assert len(centers) == 36
