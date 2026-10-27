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


def test_metadata_crop_id_when_given() -> None:
    meta = build_metadata(_jpeg_bytes(), "2026-01-01T00:00:00.000000Z", "farm-white-01",
                          "farm/zone-a-white", crop_id="basil")
    assert meta["crop_id"] == "basil"


def test_metadata_omits_crop_id_by_default() -> None:
    meta = build_metadata(_jpeg_bytes(), "2026-01-01T00:00:00.000000Z", "phone-01", "shelf-a/tray-1")
    assert "crop_id" not in meta


_PROVENANCE_KEYS = (
    "experiment_id", "biosource_id", "observation_unit_id", "treatment_id",
    "light_regime", "exposure_s", "white_balance", "gain_db", "settings_source",
)


def test_provenance_keys_are_always_emitted_as_null() -> None:
    """All nine MIAPPE-lite keys exist, with null values when not supplied."""
    meta = build_metadata(_jpeg_bytes(), "2026-01-01T00:00:00.000000Z", "phone-01", "z")
    assert set(_PROVENANCE_KEYS) <= set(meta)
    assert all(meta[key] is None for key in _PROVENANCE_KEYS)
    assert "biosource_id" in meta and meta.get("biosource_id") is None
    assert "crop_id" not in meta


def test_provenance_values_round_trip() -> None:
    """Supplied provenance values are stored verbatim, never inferred."""
    meta = build_metadata(
        _jpeg_bytes(), "2026-01-01T00:00:00.000000Z", "farm-01", "farm/zone-a",
        experiment_id="basil-2026-10", biosource_id="basil-genovese",
        observation_unit_id="farm/zone-a/slot-1", treatment_id="led-blurple-18h",
        light_regime="blurple-18/6", exposure_s=0.02, white_balance="auto",
        gain_db=None, settings_source="exif",
    )
    assert meta["experiment_id"] == "basil-2026-10"
    assert meta["biosource_id"] == "basil-genovese"
    assert meta["observation_unit_id"] == "farm/zone-a/slot-1"
    assert meta["treatment_id"] == "led-blurple-18h"
    assert meta["light_regime"] == "blurple-18/6"
    assert meta["exposure_s"] == 0.02
    assert meta["white_balance"] == "auto"
    assert meta["gain_db"] is None
    assert meta["settings_source"] == "exif"


def test_setting_without_settings_source_raises() -> None:
    """A camera setting without provenance is a false claim."""
    with pytest.raises(ValueError, match="settings_source"):
        build_metadata(
            _jpeg_bytes(), "2026-01-01T00:00:00.000000Z", "phone-01", "z",
            exposure_s=0.02,
        )


def test_unavailable_source_cannot_carry_a_setting() -> None:
    """``unavailable`` plus a non-null setting is rejected too."""
    with pytest.raises(ValueError, match="settings_source"):
        build_metadata(
            _jpeg_bytes(), "2026-01-01T00:00:00.000000Z", "phone-01", "z",
            white_balance="auto", settings_source="unavailable",
        )
