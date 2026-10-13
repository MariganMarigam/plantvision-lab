"""Color-space helpers for PlantVision.

Input images follow the OpenCV BGR convention; OpenCV's HSV hue range is
[0, 180) for uint8 images.
"""

from typing import Literal

import cv2
import numpy as np


def to_gray(img: np.ndarray) -> np.ndarray:
    """Convert a BGR image to single-channel grayscale.

    Args:
        img: BGR image array with shape ``(H, W, 3)``.

    Returns:
        Grayscale image as a ``(H, W)`` uint8 ndarray.
    """
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def to_hsv(img: np.ndarray) -> np.ndarray:
    """Convert a BGR image to HSV.

    Args:
        img: BGR image array with shape ``(H, W, 3)``.

    Returns:
        HSV image as a ``(H, W, 3)`` uint8 ndarray (H in ``[0, 180)``).

    Raises:
        ValueError: If ``img`` is not 3-channel (e.g. already grayscale);
            the message includes the offending shape.
    """
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError(f"to_hsv requires a 3-channel image, got shape={img.shape}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2HSV)


def split_channels(
    img: np.ndarray, space: Literal["bgr", "hsv", "gray"] = "bgr"
) -> dict[str, np.ndarray]:
    """Split an image into its per-channel arrays for a given color space.

    Args:
        img: Image array; ``(H, W, 3)`` for ``"bgr"``/``"hsv"``, ``(H, W)`` or
            ``(H, W, 3)`` for ``"gray"``.
        space: Color space of the input image.

    Returns:
        ``{"b", "g", "r"}`` maps for ``"bgr"``, ``{"h", "s", "v"}`` for
        ``"hsv"``, or ``{"gray": ...}`` for ``"gray"``.

    Raises:
        ValueError: If ``space`` is not one of ``"bgr"``, ``"hsv"``, ``"gray"``.
    """
    if space == "bgr":
        b, g, r = cv2.split(img)
        return {"b": b, "g": g, "r": r}
    if space == "hsv":
        h, s, v = cv2.split(to_hsv(img))
        return {"h": h, "s": s, "v": v}
    if space == "gray":
        return {"gray": to_gray(img)}
    raise ValueError(f"unknown color space: {space!r} (expected 'bgr', 'hsv', or 'gray')")


def hue_histogram(hsv: np.ndarray, bins: int = 180) -> tuple[np.ndarray, np.ndarray]:
    """Compute the histogram of hue values of an HSV image.

    Args:
        hsv: HSV image array with shape ``(H, W, 3)`` and hue in ``[0, 180)``.
        bins: Number of histogram bins over the full hue range ``[0, 180)``.

    Returns:
        Tuple ``(hist, centers)`` where ``hist`` has length ``bins`` with
        per-bin pixel counts and ``centers`` has length ``bins`` with the
        bin-center hue values.

    Raises:
        ValueError: If ``bins <= 0``.
    """
    if bins <= 0:
        raise ValueError(f"bins must be positive, got {bins}")
    hist = cv2.calcHist([hsv], [0], None, [bins], [0, 180]).ravel()
    centers = np.arange(bins)
    return hist, centers
