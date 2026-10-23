"""Metadata builder for stored capture frames."""

import hashlib
import re

import cv2
import numpy as np

# ISO-8601 UTC, Z-suffixed: 2026-10-13T18:00:00 or with fractional seconds.
_CAPTURED_AT_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z")


def build_metadata(image_bytes: bytes, captured_at: str, camera_id: str, zone_id: str,
                   crop_id: str | None = None) -> dict:
    """Build metadata for one captured frame.

    Args:
        image_bytes: Raw JPEG bytes.
        captured_at: ISO-8601 UTC timestamp ending in "Z" (device clock).
        camera_id: Camera identifier (e.g. "phone-01").
        zone_id: Grow-zone identifier (e.g. "shelf-a/tray-1").
        crop_id: Optional crop key (e.g. "basil"). Omitted from the result when
            ``None``, so legacy sidecars stay unchanged.

    Returns:
        Dict with keys sha256, captured_at, camera_id, zone_id, width,
        height, byte_size, plus ``crop_id`` when provided.

    Raises:
        ValueError: If captured_at is not ISO-8601 UTC ("...Z") or the bytes
            are not a decodable image.
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
    return meta
