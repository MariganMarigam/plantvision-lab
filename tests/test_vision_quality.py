"""Unit tests for the capture-quality module (Stage 05)."""

import cv2
import numpy as np
import pytest

from plantvision.vision.quality import blur_score, quality_flags


def _checkerboard() -> np.ndarray:
    """Sharp 100x100 uint8 checkerboard with 10 px cells (mean ~127.5)."""
    return (((np.indices((100, 100)).sum(0) // 10) % 2) * 255).astype(np.uint8)


def test_blur_score_sharp_gt_blurred() -> None:
    """A Gaussian-blurred checkerboard scores far lower and under the flag gate."""
    sharp = _checkerboard()
    blurred = cv2.GaussianBlur(sharp, (31, 31), 0)
    assert blur_score(sharp) > blur_score(blurred)
    assert blur_score(blurred) < 10.0


def test_dark_frame_flagged() -> None:
    """A uniform black frame is flagged dark (and may also carry blur)."""
    gray = np.zeros((50, 50), np.uint8)
    assert "dark" in quality_flags(gray)


def test_bright_frame_flagged() -> None:
    """A uniform white frame is flagged bright."""
    gray = np.full((50, 50), 255, np.uint8)
    assert "bright" in quality_flags(gray)


def test_ok_frame_no_flags() -> None:
    """A sharp, mid-brightness frame carries no quality flags (F3 respected)."""
    assert quality_flags(_checkerboard()) == []


def test_blur_requires_2d() -> None:
    """A 3-channel input raises ValueError (grayscale required)."""
    with pytest.raises(ValueError):
        blur_score(np.zeros((5, 5, 3), np.uint8))
