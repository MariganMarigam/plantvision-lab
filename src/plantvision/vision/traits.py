"""Shape traits for a binary plant mask (P1.5.1).

Pure ``cv2``/``numpy``; no new dependency and no import of PlantCV. The
formulas follow the *documented definitions* of the PlantCV trait vocabulary
(hull area, solidity, perimeter, equivalent ellipse, extent, component count),
reimplemented here from those definitions — no PlantCV source code is copied.
PlantCV is MPL-2.0; see ``danforthcenter/plantcv`` for the reference docs.

A mask with no foreground pixel yields ``None`` ("not measurable"), which the
time-series row builder turns into blank cells — never ``0``, ``nan`` or
``inf``. A degenerate but non-empty mask (e.g. a single pixel) still yields a
:class:`ShapeTraits` with zero-valued geometry so its component count survives.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

_COMPONENT_FRACTION = 0.005
"""A component counts when its area is at least this fraction of foreground."""


@dataclass(frozen=True)
class ShapeTraits:
    """Geometry of the largest external contour of a plant mask.

    All pixel values are full pixel units (ellipse axes are full axis lengths,
    not semi-axes). ``n_components`` counts 8-connected foreground components
    whose area is at least 0.5 % of the total foreground.
    """

    hull_area_px: float
    solidity: float
    perimeter_px: float
    ellipse_major_px: float
    ellipse_minor_px: float
    extent: float
    n_components: int


def _clamp01(value: float) -> float:
    """Clamp ``value`` into ``[0.0, 1.0]``."""
    return min(max(value, 0.0), 1.0)


def _count_components(mask: np.ndarray, foreground_px: int) -> int:
    """Count 8-connected components covering >= 0.5 % of the foreground."""
    _n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if foreground_px <= 0:
        return 0
    min_area = _COMPONENT_FRACTION * foreground_px
    return int(np.count_nonzero(stats[1:, cv2.CC_STAT_AREA] >= min_area))


def compute_traits(mask: np.ndarray) -> ShapeTraits | None:
    """Compute :class:`ShapeTraits` for a binary ``(H, W)`` plant mask.

    Args:
        mask: ``(H, W)`` uint8 mask with values ``0/1`` or ``0/255``.

    Returns:
        Trait values for the largest external contour, or ``None`` when the
        mask has no foreground pixel.

    Raises:
        ValueError: If ``mask`` is not a 2-D array.
    """
    arr = np.asarray(mask)
    if arr.ndim != 2:
        raise ValueError(f"expected a 2-D mask, got shape={arr.shape}")
    binary = np.where(arr > 0, 255, 0).astype(np.uint8)
    foreground_px = int(cv2.countNonZero(binary))
    if foreground_px == 0:
        return None

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    contour_area = float(cv2.contourArea(contour))
    n_components = _count_components(binary, foreground_px)
    if contour_area <= 0.0:
        # Degenerate contour (single pixel / a line): geometry is zero but the
        # component count is still a real observation.
        return ShapeTraits(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, n_components)

    hull_area_px = float(cv2.contourArea(cv2.convexHull(contour)))
    solidity = 0.0 if hull_area_px == 0.0 else _clamp01(contour_area / hull_area_px)
    perimeter_px = float(cv2.arcLength(contour, True))

    ellipse_major_px = ellipse_minor_px = 0.0
    if len(contour) >= 5:
        (_cx, _cy), (axis_a, axis_b), _angle = cv2.fitEllipse(contour)
        ellipse_major_px = float(max(axis_a, axis_b))
        ellipse_minor_px = float(min(axis_a, axis_b))

    _x, _y, bbox_w, bbox_h = cv2.boundingRect(contour)
    bbox_area = float(bbox_w * bbox_h)
    extent = 0.0 if bbox_area == 0.0 else _clamp01(contour_area / bbox_area)

    return ShapeTraits(
        hull_area_px=hull_area_px,
        solidity=solidity,
        perimeter_px=perimeter_px,
        ellipse_major_px=ellipse_major_px,
        ellipse_minor_px=ellipse_minor_px,
        extent=extent,
        n_components=n_components,
    )
