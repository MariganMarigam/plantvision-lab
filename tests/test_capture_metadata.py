"""Tests for the metadata builder (Stage 2 Task 2.3)."""

import cv2
import numpy as np
import pytest

from plantvision.capture.metadata import build_metadata


def _jpeg_bytes() -> bytes:
    """A real small JPEG (8x12, solid teal) for decoder-backed tests."""
    ok, buf = cv2.imencode(".jpg", np.full((8, 12, 3), (80, 160, 160), np.uint8))
    assert ok
    return buf.tobytes()


def test_metadata_sha_stable() -> None:
    data = _jpeg_bytes()
    meta1 = build_metadata(data, "2026-01-01T00:00:00.000000Z", "phone-01", "shelf-a/tray-1")
    meta2 = build_metadata(data, "2026-01-01T00:00:00.000000Z", "phone-01", "shelf-a/tray-1")
    assert meta1["sha256"] == meta2["sha256"]
    assert meta1["width"] == 12
    assert meta1["height"] == 8
    assert meta1["byte_size"] == len(data)


def test_metadata_bad_time() -> None:
    with pytest.raises(ValueError):
        build_metadata(_jpeg_bytes(), "2026-01-01", "phone-01", "shelf-a/tray-1")
