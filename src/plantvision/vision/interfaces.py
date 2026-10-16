"""Frozen perception / fiducial / measurement contract (P0).

One source of truth for the swappable perception slot, the classical
fiducial, and the geometry-only measurement.
"""

from __future__ import annotations

import math

import cv2
import numpy as np
from typing import Protocol, runtime_checkable

from plantvision.vision import segmentation as _seg, scale as _scale

MASK_BACKGROUND: int = 0
"""Background value of every contract mask (OpenCV convention)."""

MASK_FOREGROUND: int = 255
"""Foreground value of every contract mask (OpenCV convention)."""

REQUIRED_MEASUREMENT_KEYS: frozenset[str] = frozenset(
    {
        "ts",
        "projected_area_px",
        "projected_area_cm2",
        "roi_fraction_pct",
        "bbox_w",
        "bbox_h",
        "bbox_w_cm",
        "bbox_h_cm",
    }
)
"""Keys every ``measurement`` implementer must return."""


class ContractError(Exception):
    """Raised when an implementer violates the frozen interface contract."""


@runtime_checkable
class Perception(Protocol):
    """A callable that maps a BGR image to a binary plant mask."""

    def __call__(self, image: np.ndarray) -> np.ndarray: ...


@runtime_checkable
class Fiducial(Protocol):
    """A callable that maps a BGR image to a px/mm scale (or None)."""

    def __call__(self, image: np.ndarray) -> float | None: ...


@runtime_checkable
class Measurement(Protocol):
    """A callable that maps (mask, px_per_mm, ts) to the metrics dict."""

    def __call__(
        self, mask: np.ndarray, px_per_mm: float | None, ts: str | None
    ) -> dict: ...


def check_mask(mask: np.ndarray, image: np.ndarray) -> None:
    """Validate a mask against the frozen perception contract.

    Args:
        mask: Claimed ``(H, W)`` uint8 binary mask.
        image: The BGR image the mask was produced from.

    Raises:
        ContractError: If the mask is not a 2-D uint8 ndarray with the
            image's (H, W) shape and values within ``{0, 255}``.
    """
    if not isinstance(mask, np.ndarray):
        raise ContractError(f"mask is not np.ndarray: {type(mask)!r}")
    if mask.dtype != np.uint8:
        raise ContractError(f"mask dtype must be uint8, got {mask.dtype}")
    if mask.ndim != 2:
        raise ContractError(f"mask must be 2-D (H,W), got ndim={mask.ndim}")
    if mask.shape != image.shape[:2]:
        raise ContractError(f"mask shape {mask.shape} != image HxW {image.shape[:2]}")
    vals = set(np.unique(mask).tolist())
    if vals - {0, 255}:
        raise ContractError(f"mask values must be in {{0,255}}, got {sorted(vals)}")


def check_px_per_mm(value: float | None) -> None:
    """Validate a fiducial result against the frozen scale contract.

    Args:
        value: ``px_per_mm`` scale, or ``None`` when no marker was found.

    Raises:
        ContractError: If the value is neither ``None`` nor a finite
            strictly-positive number.
    """
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"px_per_mm must be None or a number, got {type(value)!r}")
    v = float(value)
    if not math.isfinite(v):
        raise ContractError(f"px_per_mm must be finite, got {v}")
    if v <= 0:
        raise ContractError(f"px_per_mm must be > 0, got {v}")


def check_measurement_result(result: dict) -> None:
    """Validate a measurement result dict against the frozen metrics contract.

    Args:
        result: Claimed measurement result mapping.

    Raises:
        ContractError: If the result is not a dict containing every required
            key with an integer pixel metric, a numeric-or-None cm metric, a
            numeric ``roi_fraction_pct``, and a ``str``-or-None ``ts``.
    """
    if not isinstance(result, dict):
        raise ContractError(f"measurement result must be a dict, got {type(result)!r}")
    missing = REQUIRED_MEASUREMENT_KEYS - set(result)
    if missing:
        raise ContractError(f"measurement result missing keys: {sorted(missing)}")
    for k in ("projected_area_px", "bbox_w", "bbox_h"):
        if isinstance(result[k], bool) or not isinstance(result[k], int):
            raise ContractError(f"{k} must be int, got {type(result[k])!r}")
    for k in ("projected_area_cm2", "bbox_w_cm", "bbox_h_cm"):
        if not (
            result[k] is None
            or isinstance(result[k], (int, float))
            and not isinstance(result[k], bool)
        ):
            raise ContractError(f"{k} must be None or number, got {type(result[k])!r}")
    if isinstance(result["roi_fraction_pct"], bool) or not isinstance(
        result["roi_fraction_pct"], (int, float)
    ):
        raise ContractError("roi_fraction_pct must be a number")
    if not (result["ts"] is None or isinstance(result["ts"], str)):
        raise ContractError("ts must be None or str")


def perception(image: np.ndarray) -> np.ndarray:
    """Classical slot-filler (Stage 05): HSV green threshold + morphology + largest component.

    Args:
        image: BGR uint8 image with shape ``(H, W, 3)``.

    Returns:
        ``(H, W)`` uint8 mask with values ``{0, 255}``.

    Raises:
        ValueError: If ``image`` is not 3-channel (propagated from
            ``segment_plant``, unchanged).
    """
    return _seg.segment_plant(image, method="hsv")


def fiducial(image: np.ndarray) -> float | None:
    """Classical slot-filler: per-frame ArUco scale (DICT_5X5_50, 45 mm; ADR 0002).

    Args:
        image: BGR or grayscale uint8 image.

    Returns:
        ``px_per_mm`` of the largest detected marker, or ``None`` when the
        frame contains no marker.
    """
    return _scale.px_per_mm(image)


def measurement(mask: np.ndarray, px_per_mm: float | None, ts: str | None) -> dict:
    """Measure a contract mask: pixel geometry plus optional cm conversion.

    The cm math intentionally mirrors ``metrics._cm_metrics`` so both paths
    produce identical numbers (see plan risk R1).

    Args:
        mask: ``(H, W)`` uint8 binary mask with values ``{0, 255}``.
        px_per_mm: Frame scale, or ``None`` when no marker was found.
        ts: Timestamp string to echo into the result, or ``None``.

    Returns:
        Dict with the required measurement keys: ``ts``, ``projected_area_px``,
        ``projected_area_cm2``, ``roi_fraction_pct``, ``bbox_w``, ``bbox_h``,
        ``bbox_w_cm``, ``bbox_h_cm`` (cm metrics are ``None`` when unscaled).

    Raises:
        ContractError: If the mask is malformed, has zero area, or the scale
            is not ``None``/finite/positive (propagated from
            ``check_px_per_mm``).
    """
    if not isinstance(mask, np.ndarray) or mask.ndim != 2:
        raise ContractError("mask must be a 2-D ndarray")
    h_px, w_px = mask.shape
    if h_px * w_px == 0:
        raise ContractError("mask has zero area")
    if px_per_mm is not None:
        check_px_per_mm(px_per_mm)
    area_px = int(cv2.countNonZero(mask))
    if area_px > 0:
        _x, _y, bw, bh = cv2.boundingRect(mask)
    else:
        bw = 0
        bh = 0
    roi_fraction_pct = 100.0 * area_px / float(h_px * w_px)
    if px_per_mm is None:
        area_cm2 = bw_cm = bh_cm = None
    else:
        area_cm2 = area_px / (px_per_mm**2) / 100.0
        bw_cm = bw / px_per_mm / 10.0
        bh_cm = bh / px_per_mm / 10.0
    return {
        "ts": ts,
        "projected_area_px": area_px,
        "projected_area_cm2": area_cm2,
        "roi_fraction_pct": roi_fraction_pct,
        "bbox_w": bw,
        "bbox_h": bh,
        "bbox_w_cm": bw_cm,
        "bbox_h_cm": bh_cm,
    }
