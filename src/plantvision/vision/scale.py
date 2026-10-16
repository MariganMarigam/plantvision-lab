"""Per-frame physical scale calibration via ArUco marker detection (Stage 05).

Detects ``DICT_5X5_50`` markers and converts the largest marker's pixel side
to ``px_per_mm`` using the known printed marker size (ADR 0002: recompute for
every frame; a frame without a marker exposes pixel-only metrics).
"""

from __future__ import annotations

import cv2
import numpy as np


def _resolve_dict(dict_name: str) -> int:
    """Resolve a predefined-dictionary attribute name to its OpenCV constant.

    Args:
        dict_name: Attribute name on ``cv2.aruco``, e.g. ``"DICT_5X5_50"``.

    Returns:
        The OpenCV predefined-dictionary identifier.

    Raises:
        ValueError: If the name is not a predefined OpenCV ArUco dictionary.
    """
    try:
        return getattr(cv2.aruco, dict_name)
    except AttributeError as exc:
        raise ValueError(f"unknown ArUco dict: {dict_name!r}") from exc


def marker_side_px(corners: np.ndarray) -> float:
    """Mean of the four side lengths of one marker's corner quadrilateral.

    Args:
        corners: ``(4, 2)`` array of marker corner coordinates (float).

    Returns:
        Mean side length in pixels.
    """
    return float(
        np.mean([np.linalg.norm(corners[(i + 1) % 4] - corners[i]) for i in range(4)])
    )


def detect_markers(img: np.ndarray, dict_name: str = "DICT_5X5_50") -> list[dict]:
    """Detect ArUco markers of the given predefined dictionary in an image.

    Args:
        img: BGR or grayscale uint8 image.
        dict_name: Predefined dictionary attribute name on ``cv2.aruco``.

    Returns:
        One dict per detected marker: ``{"id": int, "corners": (4, 2) float64}``.
        Empty list when no marker is found.

    Raises:
        ValueError: If ``dict_name`` is unknown.
    """
    dictionary = cv2.aruco.getPredefinedDictionary(_resolve_dict(dict_name))
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    corners, ids, _ = detector.detectMarkers(img)
    if ids is None:
        return []
    markers: list[dict] = []
    for i, mid in enumerate(ids):
        markers.append(
            {"id": int(mid), "corners": corners[i].reshape(4, 2).astype(np.float64)}
        )
    return markers


def px_per_mm(
    img: np.ndarray, marker_size_mm: float = 45.0, dict_name: str = "DICT_5X5_50"
) -> float | None:
    """Compute the frame's pixel-per-millimeter scale from its largest marker.

    Args:
        img: BGR or grayscale uint8 image.
        marker_size_mm: Physical side length of the printed marker in mm.
        dict_name: Predefined dictionary attribute name on ``cv2.aruco``.

    Returns:
        ``px_per_mm`` of the largest detected marker, or ``None`` when the
        frame contains no detectable marker (never a fabricated number).

    Raises:
        ValueError: If ``marker_size_mm <= 0`` or ``dict_name`` is unknown.
    """
    if marker_size_mm <= 0:
        raise ValueError("marker_size_mm must be > 0")
    markers = detect_markers(img, dict_name)
    if not markers:
        return None
    best = max(markers, key=lambda m: marker_side_px(m["corners"]))
    return marker_side_px(best["corners"]) / marker_size_mm
