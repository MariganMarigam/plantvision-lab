"""Classic (non-NN) plant segmentation for PlantVision Stage 05.

Pipeline: HSV green threshold and/or ExG index -> morphological open/close ->
largest connected component. All masks are ``(H, W)`` uint8 with values
``{0, 255}`` (OpenCV convention).
"""

from __future__ import annotations

import cv2
import numpy as np

DEFAULT_HSV_LOWER: tuple[int, int, int] = (25, 40, 40)
DEFAULT_HSV_UPPER: tuple[int, int, int] = (95, 255, 255)


def green_mask_hsv(
    img: np.ndarray,
    lower: tuple[int, int, int] = DEFAULT_HSV_LOWER,
    upper: tuple[int, int, int] = DEFAULT_HSV_UPPER,
) -> np.ndarray:
    """Threshold the green band in OpenCV HSV space.

    Args:
        img: BGR uint8 image with shape ``(H, W, 3)``.
        lower: Inclusive lower HSV bounds, H in ``[0, 180)``.
        upper: Inclusive upper HSV bounds.

    Returns:
        ``(H, W)`` uint8 mask with values ``{0, 255}``.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, np.array(lower, np.uint8), np.array(upper, np.uint8))


def exg_mask(img: np.ndarray, threshold: float = 20.0) -> np.ndarray:
    """Threshold the Excess Green index ``ExG = 2G - R - B``.

    Args:
        img: BGR uint8 image with shape ``(H, W, 3)``.
        threshold: Minimum ExG value (0..255 scale) for a pixel to count as plant.

    Returns:
        ``(H, W)`` uint8 mask with values ``{0, 255}``.
    """
    b, g, r = cv2.split(img)
    b = b.astype(np.float32)
    g = g.astype(np.float32)
    r = r.astype(np.float32)
    exg = 2.0 * g - r - b
    return np.where(exg >= threshold, 255, 0).astype(np.uint8)


def clean_mask(mask: np.ndarray, open_ksize: int = 5, close_ksize: int = 7) -> np.ndarray:
    """Apply morphological open then close with elliptical kernels.

    Args:
        mask: Binary ``(H, W)`` uint8 mask.
        open_ksize: Kernel size for the opening (removes specks).
        close_ksize: Kernel size for the closing (fills holes).

    Returns:
        Cleaned ``(H, W)`` uint8 mask with values ``{0, 255}``.
    """
    k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_ksize, open_ksize))
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_ksize, close_ksize))
    opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k_open)
    return cv2.morphologyEx(opened, cv2.MORPH_CLOSE, k_close)


def largest_component(mask: np.ndarray) -> np.ndarray:
    """Keep only the largest 8-connected foreground component.

    Args:
        mask: Binary ``(H, W)`` uint8 mask.

    Returns:
        ``(H, W)`` uint8 mask containing only the largest component, or an
        all-zero mask when the input has no foreground.
    """
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        (mask > 0).astype(np.uint8), connectivity=8
    )
    if n <= 1:
        return np.zeros_like(mask)
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(labels == best, 255, 0).astype(np.uint8)


def segment_plant(
    img: np.ndarray,
    method: str = "hsv",
    hsv_lower: tuple[int, int, int] = DEFAULT_HSV_LOWER,
    hsv_upper: tuple[int, int, int] = DEFAULT_HSV_UPPER,
    exg_threshold: float = 20.0,
    open_ksize: int = 5,
    close_ksize: int = 7,
) -> np.ndarray:
    """Segment the plant from a BGR frame using the configured method.

    Args:
        img: BGR uint8 image with shape ``(H, W, 3)``.
        method: One of ``"hsv"``, ``"exg"``, ``"hsv_or_exg"``.
        hsv_lower: Lower HSV bounds for the HSV method.
        hsv_upper: Upper HSV bounds for the HSV method.
        exg_threshold: ExG threshold for the ExG method.
        open_ksize: Morphological opening kernel size (odd, >= 1).
        close_ksize: Morphological closing kernel size (odd, >= 1).

    Returns:
        ``(H, W)`` uint8 mask with values ``{0, 255}``: threshold -> clean ->
        largest connected component. All-zero when no plant is found.

    Raises:
        ValueError: If ``img`` is not 3-channel or ``method`` is unknown.
    """
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError(f"expected (H, W, 3) BGR image, got shape={img.shape}")
    if method == "hsv":
        mask = green_mask_hsv(img, hsv_lower, hsv_upper)
    elif method == "exg":
        mask = exg_mask(img, exg_threshold)
    elif method == "hsv_or_exg":
        mask = cv2.bitwise_or(
            green_mask_hsv(img, hsv_lower, hsv_upper), exg_mask(img, exg_threshold)
        )
    else:
        raise ValueError(f"unknown method: {method!r}")
    mask = clean_mask(mask, open_ksize, close_ksize)
    return largest_component(mask)
