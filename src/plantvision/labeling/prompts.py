"""Box-prompt priors for SAM2: classical HSV, full frame, manual, ridge, marker.

``roi_box`` is the frozen classical prior (HSV green-mask bbox expanded
for SAM2). ``prior_box`` dispatches across the P1.1 strategies and always
reports which prior actually produced the box, so proposals stay honest
when an automatic prior falls back to the full frame.

All coordinates are inclusive pixel indices.
"""

from __future__ import annotations

import cv2
import numpy as np

from plantvision.vision.interfaces import perception

BOX_STRATEGIES: tuple[str, ...] = (
    "classical",
    "full",
    "manual",
    "ridge",
    "marker",
)
"""Strategies accepted by :func:`prior_box`."""

MARKER_LEFT: float = 2.2
MARKER_RIGHT: float = 3.2
MARKER_ABOVE: float = 5.2
MARKER_BELOW: float = 0.4
"""Marker-box offsets to the left/right/above/below, as multiples of ``s``."""

MIN_MARKER_SIDE_PX: int = 8
"""Smallest accepted marker mean side ``s`` in pixels (guards degeneracy)."""

MIN_BOX_SIDE_PX: int = 8
"""Smallest accepted marker-derived box side in pixels after clipping."""

Prior = tuple[tuple[int, int, int, int], str]
"""A prompt box plus the ``box_source`` label that actually produced it."""


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


def _check_image(image_bgr: np.ndarray) -> None:
    """Raise ``ValueError`` unless ``image_bgr`` is ``(H, W, 3)``."""
    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError(
            f"expected (H, W, 3) BGR image, got shape={image_bgr.shape}"
        )


def _check_prior_params(expand: float, min_area_frac: float) -> None:
    """Validate the shared automatic-prior parameters."""
    if not 0.0 <= expand <= 1.0:
        raise ValueError(f"expand must be in [0.0, 1.0], got {expand}")
    if not 0.0 <= min_area_frac < 1.0:
        raise ValueError(
            f"min_area_frac must be in [0.0, 1.0), got {min_area_frac}"
        )


def _expand_box(
    x: int,
    y: int,
    w: int,
    h: int,
    width: int,
    height: int,
    expand: float,
) -> tuple[int, int, int, int]:
    """Expand a ``(x, y, w, h)`` rect and clip it to the frame."""
    dx = int(round(w * expand))
    dy = int(round(h * expand))
    return (
        max(0, x - dx),
        max(0, y - dy),
        min(width - 1, x + w - 1 + dx),
        min(height - 1, y + h - 1 + dy),
    )


def _manual_box(
    box: tuple[int, int, int, int] | None, width: int, height: int
) -> tuple[int, int, int, int]:
    """Validate a manual box, clip it to the frame, and return it."""
    if box is None:
        raise ValueError("strategy='manual' requires box=(x1, y1, x2, y2)")
    if not isinstance(box, (tuple, list)) or len(box) != 4:
        raise ValueError(f"box must be four integers, got {box!r}")
    if any(isinstance(v, bool) or not isinstance(v, int) for v in box):
        raise ValueError(f"box must be four integers, got {box!r}")
    x1, y1, x2, y2 = box
    if x1 > x2 or y1 > y2:
        raise ValueError(f"box must satisfy x1<=x2 and y1<=y2, got {box!r}")
    if x2 < 0 or y2 < 0 or x1 >= width or y1 >= height:
        raise ValueError(f"box {box!r} lies outside frame {width}x{height}")
    return (
        min(max(x1, 0), width - 1),
        min(max(y1, 0), height - 1),
        min(max(x2, 0), width - 1),
        min(max(y2, 0), height - 1),
    )


def _texture_energy(channel: np.ndarray, window: int) -> np.ndarray:
    """Local standard deviation of one channel, normalised to ``0..255``.

    Local variance is the "ridge" response: it is high on leaf edges and
    leaf clumps and near zero on smooth grow-room surfaces.
    """
    values = channel.astype(np.float32)
    mean = cv2.blur(values, (window, window))
    mean_sq = cv2.blur(values * values, (window, window))
    std = np.sqrt(np.maximum(mean_sq - mean * mean, 0.0))
    peak = float(std.max())
    if peak <= 0.0:
        return np.zeros(channel.shape, dtype=np.uint8)
    return np.clip(std * (255.0 / peak), 0, 255).astype(np.uint8)


def _ridge_box(
    image_bgr: np.ndarray, expand: float, min_area_frac: float
) -> tuple[int, int, int, int] | None:
    """Blurple-safe prior: brightness/saturation texture ridge -> largest blob.

    Algorithm (no BGR or green-channel test is performed):

    1. Convert to HSV and take the value (V) and saturation (S) channels.
    2. Compute each channel's local standard deviation over an odd window
       of about 2% of the short side, then normalise to ``0..255``. This
       is the brightness/saturation "ridge" response: leaf texture lights
       up, flat trays/walls do not, regardless of the light's colour.
    3. Sum the two responses with saturation (``cv2.add``) and split them
       with Otsu's threshold.
    4. Close the ridge mask so adjacent leaf edges form blobs, drop
       specks with an opening, and take the largest connected component.
    5. Reject components below ``min_area_frac`` of the frame; otherwise
       return their expanded, frame-clipped bounding box.

    Returns:
        Inclusive ``(x1, y1, x2, y2)`` box, or ``None`` when no component
        is large enough.
    """
    height, width = image_bgr.shape[:2]
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    window = max(3, int(round(min(height, width) * 0.02)))
    if window % 2 == 0:
        window += 1
    energy = cv2.add(
        _texture_energy(hsv[:, :, 1], window),
        _texture_energy(hsv[:, :, 2], window),
    )
    _, mask = cv2.threshold(
        energy, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (window, window))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask, connectivity=8
    )
    if count <= 1:
        return None
    areas = stats[1:, cv2.CC_STAT_AREA]
    best = int(np.argmax(areas)) + 1
    if int(stats[best, cv2.CC_STAT_AREA]) < min_area_frac * width * height:
        return None
    return _expand_box(
        int(stats[best, cv2.CC_STAT_LEFT]),
        int(stats[best, cv2.CC_STAT_TOP]),
        int(stats[best, cv2.CC_STAT_WIDTH]),
        int(stats[best, cv2.CC_STAT_HEIGHT]),
        width,
        height,
        expand,
    )


def _marker_box(image_bgr: np.ndarray) -> tuple[int, int, int, int] | None:
    """Marker-relative blurple prior: box offset above the ArUco tag.

    The capture rig mounts a ``DICT_5X5_50`` ArUco marker beside the basil
    tray. For the largest detected marker, with bounding-box size ``w`` x
    ``h``, centre ``(cx, cy)`` and scale ``s = (w + h) / 2``, the plant box
    is::

        (cx - 2.2s, cy - 5.2s, cx + 3.2s, cy - 0.4s)

    (inclusive pixel indices), clipped to the frame. Detections whose mean
    side ``s`` is below ``MIN_MARKER_SIDE_PX``, or whose clipped box side
    is below ``MIN_BOX_SIDE_PX``, are rejected as degenerate.

    Args:
        image_bgr: BGR uint8 image with shape ``(H, W, 3)``.

    Returns:
        Inclusive ``(x1, y1, x2, y2)`` box, or ``None`` when no usable
        marker is detected.
    """
    aruco = getattr(cv2, "aruco", None)
    if aruco is None:
        return None
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_5X5_50)
    if hasattr(aruco, "ArucoDetector"):
        detector = aruco.ArucoDetector(dictionary, aruco.DetectorParameters())
        corners, ids, _ = detector.detectMarkers(image_bgr)
    else:
        corners, ids, _ = aruco.detectMarkers(image_bgr, dictionary)
    if ids is None or len(corners) == 0:
        return None
    rects = [
        cv2.boundingRect(pts.reshape(-1, 2).astype(np.float32))
        for pts in corners
    ]
    x, y, w, h = max(rects, key=lambda rect: rect[2] * rect[3])
    s = (w + h) / 2.0
    if s < MIN_MARKER_SIDE_PX:
        return None
    cx, cy = x + w / 2.0, y + h / 2.0
    height, width = image_bgr.shape[:2]
    x1 = max(0, int(round(cx - MARKER_LEFT * s)))
    y1 = max(0, int(round(cy - MARKER_ABOVE * s)))
    x2 = min(width - 1, int(round(cx + MARKER_RIGHT * s)))
    y2 = min(height - 1, int(round(cy - MARKER_BELOW * s)))
    if x2 - x1 + 1 < MIN_BOX_SIDE_PX or y2 - y1 + 1 < MIN_BOX_SIDE_PX:
        return None
    return (x1, y1, x2, y2)


def prior_box(
    image_bgr: np.ndarray,
    *,
    strategy: str = "classical",
    box: tuple[int, int, int, int] | None = None,
    expand: float = 0.15,
    min_area_frac: float = 0.005,
) -> Prior:
    """Compute a SAM2 box prompt and report the source that produced it.

    Args:
        image_bgr: BGR uint8 image with shape ``(H, W, 3)``.
        strategy: One of :data:`BOX_STRATEGIES`:

            - ``"classical"``: frozen HSV green-mask prior (:func:`roi_box`).
            - ``"full"``: the whole frame.
            - ``"manual"``: the caller-supplied ``box``, validated and
              clipped to the frame.
            - ``"ridge"``: blurple-safe brightness/saturation texture ridge
              plus largest connected component (see :func:`_ridge_box`).
            - ``"marker"``: box offset above the ``DICT_5X5_50`` ArUco tag
              mounted beside the tray (see :func:`_marker_box`).
        box: Manual inclusive ``(x1, y1, x2, y2)`` box; required and only
            used when ``strategy == "manual"``.
        expand: Expansion factor for automatic priors, in ``[0.0, 1.0]``.
        min_area_frac: Minimum foreground fraction of the frame for
            automatic priors, in ``[0.0, 1.0)``.

    Returns:
        ``(box, source)`` where ``source`` is the label of the prior that
        actually produced the box: ``"hsv"``, ``"full_frame"``,
        ``"manual"``, ``"ridge"`` or ``"marker"``. Automatic strategies fall
        back to the full frame, labelled ``"full_frame"``.

    Raises:
        ValueError: If the image is not 3-channel, the strategy is unknown,
            a numeric parameter is out of range, or the manual box is
            missing, malformed, inverted, or entirely outside the frame.
    """
    _check_image(image_bgr)
    if strategy not in BOX_STRATEGIES:
        raise ValueError(
            f"strategy must be one of {BOX_STRATEGIES}, got {strategy!r}"
        )
    _check_prior_params(expand, min_area_frac)
    height, width = image_bgr.shape[:2]
    full = (0, 0, width - 1, height - 1)
    if strategy == "full":
        return full, "full_frame"
    if strategy == "manual":
        return _manual_box(box, width, height), "manual"
    if strategy == "ridge":
        candidate = _ridge_box(image_bgr, expand, min_area_frac)
        return (candidate, "ridge") if candidate is not None else (full, "full_frame")
    if strategy == "marker":
        candidate = _marker_box(image_bgr)
        return (candidate, "marker") if candidate is not None else (full, "full_frame")
    candidate = roi_box(image_bgr, expand=expand, min_area_frac=min_area_frac)
    return (candidate, "hsv") if candidate is not None else (full, "full_frame")
