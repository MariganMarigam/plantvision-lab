"""Tests for plantvision.vision.io image I/O helpers."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from plantvision.vision.io import ImageReadError, image_info, load_image


def test_load_save_roundtrip(tmp_path: Path) -> None:
    """A random 4x6x3 uint8 PNG written via cv2.imwrite loads back unchanged in shape/dtype."""
    img = np.random.randint(0, 255, size=(4, 6, 3), dtype=np.uint8)
    png = tmp_path / "roundtrip.png"
    assert cv2.imwrite(str(png), img)

    loaded = load_image(png)

    assert loaded.shape == (4, 6, 3)
    assert loaded.dtype == np.uint8


def test_image_info_grayscale() -> None:
    """A 2-D grayscale array reports channels == 1 without indexing shape[2]."""
    info = image_info(np.zeros((3, 5), dtype=np.uint8))

    assert info["channels"] == 1


def test_load_missing_raises() -> None:
    """A nonexistent path raises ImageReadError, never returns None."""
    with pytest.raises(ImageReadError):
        load_image(tmp_path := Path("does") / "not" / "exist.png")
