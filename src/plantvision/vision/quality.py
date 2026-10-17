"""Capture-quality flags (blur / dark / bright) for PlantVision Stage 05.

Blur is scored as the Laplacian variance of the grayscale frame; brightness as
its mean intensity. Thresholds live in ``configs/pipeline.yaml`` — notably
``blur_lapvar_min`` sits below the measured low-texture floor (F3) so flat but
sharp scenes are not falsely flagged.
"""

from __future__ import annotations

import cv2
import numpy as np


def _as_gray(gray: np.ndarray) -> np.ndarray:
    """Validate and return a 2-D grayscale array.

    Args:
        gray: Array expected to have shape ``(H, W)``.

    Returns:
        The same array, validated.

    Raises:
        ValueError: If the array is not 2-D grayscale.
    """
    if gray.ndim != 2:
        raise ValueError(f"expected (H,W) grayscale, got shape={gray.shape}")
    return gray


def blur_score(gray: np.ndarray) -> float:
    """Laplacian variance of the grayscale frame (higher = more texture/sharpness).

    Args:
        gray: ``(H, W)`` uint8 grayscale frame.

    Returns:
        Variance of the Laplacian response (float).

    Raises:
        ValueError: If the input is not 2-D.
    """
    return float(cv2.Laplacian(_as_gray(gray), cv2.CV_64F).var())


def brightness_score(gray: np.ndarray) -> float:
    """Mean pixel intensity of the grayscale frame.

    Args:
        gray: ``(H, W)`` uint8 grayscale frame.

    Returns:
        Mean intensity (float).

    Raises:
        ValueError: If the input is not 2-D.
    """
    return float(_as_gray(gray).mean())


def quality_flags(
    gray: np.ndarray,
    blur_lapvar_min: float = 10.0,
    brightness_min: float = 40.0,
    brightness_max: float = 220.0,
) -> list[str]:
    """Flag a frame's capture-quality problems.

    Args:
        gray: ``(H, W)`` uint8 grayscale frame.
        blur_lapvar_min: Laplacian variance below this => ``"blur"``.
        brightness_min: Mean intensity below this => ``"dark"``.
        brightness_max: Mean intensity above this => ``"bright"``.

    Returns:
        Subset of ``["blur", "dark", "bright"]`` (a frame may carry several).

    Raises:
        ValueError: If the input is not 2-D.
    """
    flags: list[str] = []
    if blur_score(gray) < blur_lapvar_min:
        flags.append("blur")
    b = brightness_score(gray)
    if b < brightness_min:
        flags.append("dark")
    elif b > brightness_max:
        flags.append("bright")
    return flags


def red_dominance(bgr: np.ndarray) -> float:
    """Mean(R)/mean(G) of a BGR frame (red-grow-light indicator).

    Informational only: a value at or above the configured threshold is a
    red-light hint, never a rejection.

    Args:
        bgr: ``(H, W, 3)`` uint8 BGR frame (OpenCV channel order).

    Returns:
        ``mean(R) / max(mean(G), 1.0)`` — finite even for an all-black frame
        (the ``max`` guards against ZeroDivisionError).

    Raises:
        ValueError: If the input is not a 3-channel BGR array.
    """
    if bgr.ndim != 3 or bgr.shape[2] != 3:
        raise ValueError(f"expected (H,W,3) BGR, got shape={bgr.shape}")
    mean_r = float(bgr[:, :, 2].mean())  # OpenCV BGR: index 2 is red.
    mean_g = float(bgr[:, :, 1].mean())
    return mean_r / max(mean_g, 1.0)
