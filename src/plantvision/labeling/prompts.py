"""Classical ROI box prior: HSV ``perception()`` bbox expanded for SAM2.

Converts the frozen classical plant mask into a box prompt. The box is
the tight bounding rect of the mask, expanded by a factor and clipped to
the frame. All coordinates are inclusive pixel indices.
"""

from __future__ import annotations

import cv2
import numpy as np

from plantvision.vision.interfaces import perception


def roi_box(
    image_bgr: np.ndarray,
    expand: float = 0.15,
    min_area_frac: float = 0.005,
) -> tuple[int, int, int, int] | None:
    """Compute the plant ROI box prior for a single-frame image.

    Args:
        image_bgr: BGR uint8 image with shape ``(H, W, 3)``.
        expand: Expansion factor applied to the mask bounding rect,
            in ``[0.0, 1.0]``.
        min_area_frac: Minimum foreground fraction of ``perception``'s
            mask (in ``[0.0, 1.0)``) to accept the prior.

    Returns:
        Inclusive ``(x1, y1, x2, y2)`` integer box, or ``None`` when the
        classical mask covers less than ``min_area_frac`` of the frame.

    Raises:
        ValueError: If ``image_bgr`` is not 3-channel or a parameter is
            outside its documented range (mirrors
            ``segmentation.segment_plant`` behaviour).
    """
    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError(
            f"expected (H, W, 3) BGR image, got shape={image_bgr.shape}"
        )
    if not 0.0 <= expand <= 1.0:
        raise ValueError(f"expand must be in [0.0, 1.0], got {expand}")
    if not 0.0 <= min_area_frac < 1.0:
        raise ValueError(
            f"min_area_frac must be in [0.0, 1.0), got {min_area_frac}"
        )
    mask = perception(image_bgr)
    height, width = image_bgr.shape[:2]
    if cv2.countNonZero(mask) < min_area_frac * width * height:
        return None
    x, y, w, h = cv2.boundingRect(mask)
    dx = int(round(w * expand))
    dy = int(round(h * expand))
    x1 = max(0, x - dx)
    y1 = max(0, y - dy)
    x2 = min(width - 1, x + w - 1 + dx)
    y2 = min(height - 1, y + h - 1 + dy)
    return (x1, y1, x2, y2)


def full_frame_box(image_bgr: np.ndarray) -> tuple[int, int, int, int]:
    """Return the full frame as an inclusive box ``(0, 0, W-1, H-1)``."""
    height, width = image_bgr.shape[:2]
    return (0, 0, width - 1, height - 1)
