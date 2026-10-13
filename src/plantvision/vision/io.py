"""Image I/O helpers for PlantVision.

All images are handled in OpenCV convention: BGR channel order, uint8 dtype.
"""

from pathlib import Path

import cv2
import numpy as np


class ImageReadError(Exception):
    """Raised when an image cannot be read from or written to disk."""


def load_image(path: str | Path) -> np.ndarray:
    """Load an image from disk without altering its channels or depth.

    Args:
        path: File path of the image to read.

    Returns:
        Decoded image as a BGR uint8 ndarray with shape ``(H, W, 3)`` or a
        grayscale/pixel-mask image with shape ``(H, W)``, depending on source.

    Raises:
        ImageReadError: If the file does not exist or cannot be decoded.
    """
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ImageReadError(f"cannot read image: {path}")
    return img


def save_image(img: np.ndarray, path: str | Path) -> Path:
    """Write an image to disk, creating parent directories as needed.

    Args:
        img: Image array to write (any depth/channel count ``cv2.imwrite`` supports).
        path: Destination file path.

    Returns:
        The destination path as a :class:`~pathlib.Path`.

    Raises:
        ImageReadError: If ``cv2.imwrite`` fails (unsupported dtype, bad path).
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(dest), img):
        raise ImageReadError(f"cannot write image: {dest}")
    return dest


def image_info(img: np.ndarray) -> dict:
    """Summarize an image array's shape, dtype, and value range.

    Args:
        img: Image array to inspect, ``(H, W)`` or ``(H, W, C)``.

    Returns:
        Dict with keys ``height``, ``width``, ``channels``, ``dtype``,
        ``min``, ``max``, ``mean``.

    Raises:
        ValueError: If the array is empty (no pixels to summarize).
    """
    if img.size == 0:
        raise ValueError(f"image is empty, shape={img.shape}")
    height, width = img.shape[0], img.shape[1]
    channels = img.shape[2] if img.ndim == 3 else 1
    return {
        "height": height,
        "width": width,
        "channels": channels,
        "dtype": str(img.dtype),
        "min": float(img.min()),
        "max": float(img.max()),
        "mean": float(img.mean()),
    }
