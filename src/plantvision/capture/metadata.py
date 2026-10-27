"""Metadata builder for stored capture frames.

Provenance keys follow the MIAPPE 1.2 vocabulary (field *names* only; see
``github.com/MIAPPE/MIAPPE``, doi:10.1111/nph.16544). Values are never required,
never inferred and never defaulted to a crop literal: absent information is
emitted as JSON ``null`` so the gap stays visible.
"""

import hashlib
import re

import cv2
import numpy as np

# ISO-8601 UTC, Z-suffixed: 2026-10-13T18:00:00 or with fractional seconds.
_CAPTURED_AT_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z")

_SETTING_SOURCES = frozenset({"exif", "app", "manual"})


def build_metadata(
    image_bytes: bytes,
    captured_at: str,
    camera_id: str,
    zone_id: str,
    crop_id: str | None = None,
    *,
    experiment_id: str | None = None,
    biosource_id: str | None = None,
    observation_unit_id: str | None = None,
    treatment_id: str | None = None,
    light_regime: str | None = None,
    exposure_s: float | None = None,
    white_balance: str | None = None,
    gain_db: float | None = None,
    settings_source: str | None = None,
) -> dict:
    """Build metadata for one captured frame.

    Args:
        image_bytes: Raw JPEG bytes.
        captured_at: ISO-8601 UTC timestamp ending in "Z" (device clock).
        camera_id: Camera identifier (e.g. "phone-01").
        zone_id: Grow-zone identifier (e.g. "shelf-a/tray-1").
        crop_id: Optional crop key (e.g. "basil"). Omitted from the result when
            ``None``, so legacy sidecars stay unchanged.
        experiment_id: MIAPPE experiment/investigation id (e.g. "basil-2026-10").
        biosource_id: MIAPPE biological source / cultivar (e.g. "basil-genovese").
        observation_unit_id: MIAPPE observation unit, zone + slot.
        treatment_id: MIAPPE treatment / factor level.
        light_regime: Photoperiod/spectrum label (never inferred).
        exposure_s: Camera exposure time in seconds (EXIF ExposureTime).
        white_balance: ``"auto"`` or ``"manual"`` (EXIF WhiteBalance).
        gain_db: Camera gain in dB; ``None`` for phone EXIF (no documented
            ISO -> dB conversion, so it is never invented).
        settings_source: Provenance of the three settings above:
            ``"exif"`` | ``"app"`` | ``"manual"`` | ``"unavailable"``.

    Returns:
        Dict with keys sha256, captured_at, camera_id, zone_id, width, height,
        byte_size, ``crop_id`` when provided, plus the nine MIAPPE-lite
        provenance keys (always present, value or ``None``).

    Raises:
        ValueError: If captured_at is not ISO-8601 UTC ("...Z"), the bytes are
            not a decodable image, or a camera setting is supplied without a
            provenance source.
    """
    if not _CAPTURED_AT_RE.fullmatch(captured_at):
        raise ValueError(
            f"captured_at is not ISO-8601 UTC ending in Z (e.g. 2026-10-13T18:00:00.000000Z): {captured_at!r}"
        )
    arr = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise ValueError("undecodable image")
    height, width = arr.shape[:2]
    meta = {
        "sha256": hashlib.sha256(image_bytes).hexdigest(),
        "captured_at": captured_at,
        "camera_id": camera_id,
        "zone_id": zone_id,
        "width": int(width),
        "height": int(height),
        "byte_size": len(image_bytes),
    }
    if crop_id is not None:
        meta["crop_id"] = crop_id
    meta.update(
        experiment_id=experiment_id,
        biosource_id=biosource_id,
        observation_unit_id=observation_unit_id,
        treatment_id=treatment_id,
        light_regime=light_regime,
        exposure_s=exposure_s,
        white_balance=white_balance,
        gain_db=gain_db,
        settings_source=settings_source,
    )
    _validate_settings(exposure_s, white_balance, gain_db, settings_source)
    return meta


def _validate_settings(
    exposure_s: float | None,
    white_balance: str | None,
    gain_db: float | None,
    settings_source: str | None,
) -> None:
    """Reject a camera setting that has no real provenance source.

    Raises:
        ValueError: If a setting is non-null but ``settings_source`` is missing
            or claims ``"unavailable"``.
    """
    present = exposure_s is not None or white_balance is not None or gain_db is not None
    if present and settings_source not in _SETTING_SOURCES:
        raise ValueError(
            "camera setting supplied without provenance: "
            f"settings_source={settings_source!r} (a setting without provenance "
            "is a false claim)"
        )
