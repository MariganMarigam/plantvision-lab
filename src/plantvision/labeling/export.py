"""YOLO-seg polygon export for accepted label masks (plan Section 4.6).

Everything is regenerable from ``manifest.csv`` + the frame JPEGs +
mask PNGs; images are copied with ``shutil.copy2`` (byte-identical) and
no EXIF transform is applied anywhere.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from plantvision.labeling.store import read_mask

POLY_EPS_RATIO: float = 0.002
"""approxPolyDP epsilon as a fraction of the contour arc length."""

MIN_CONTOUR_AREA_FRAC: float = 0.005
"""Minimum contour area as a fraction of the mask pixel count."""

SPLITS: tuple[str, ...] = ("train", "val", "test")


def mask_to_polygon(
    mask: np.ndarray, width: int, height: int
) -> "list[tuple[float, float]] | None":
    """Extract the simplified external contour as normalized points.

    Args:
        mask: ``(H, W)`` uint8 mask in ``{0, 255}``.
        width: Frame width used for x normalization.
        height: Frame height used for y normalization.

    Returns:
        ``[(x, y), ...]`` with coordinates clipped to ``[0.0, 1.0``, plus
        ``None`` when the mask is degenerate: no contour, contour area
        below ``max(4.0, MIN_CONTOUR_AREA_FRAC * countNonZero(mask))``, or
        fewer than 3 points after simplification.
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(contour)
    if area < max(4.0, MIN_CONTOUR_AREA_FRAC * cv2.countNonZero(mask)):
        return None
    approx = cv2.approxPolyDP(
        contour, POLY_EPS_RATIO * cv2.arcLength(contour, True), True
    )
    if len(approx) < 3:
        return None

    def clip(value: float) -> float:
        return float(min(1.0, max(0.0, value)))

    points = []
    for point in approx:
        x = clip(float(point[0][0]) / max(1, width - 1))
        y = clip(float(point[0][1]) / max(1, height - 1))
        points.append((x, y))
    return points


def yolo_seg_line(
    points: "list[tuple[float, float]]", class_id: int = 0
) -> str:
    """Format one YOLO-seg label line (normalized points, 6 decimals)."""
    body = " ".join(f"{x:.6f} {y:.6f}" for x, y in points)
    return f"{class_id} {body}"


def export_yolo_seg(
    manifest_rows: "list[dict[str, Any]]",
    originals: Path,
    labels_root: Path,
    out_dir: Path,
    masks_out: Path,
) -> "dict[str, Any]":
    """Export accepted manifest rows to YOLO-seg images/labels + PNG masks.

    Args:
        manifest_rows: Rows from ``manifest.csv`` (dicts).
        originals: Dataset root in front of each ``frame_relpath``.
        labels_root: Label store root in front of each ``mask_relpath``.
        out_dir: Destination of ``images/<split>``, ``labels/<split>``,
            ``data.yaml``.
        masks_out: Destination of ``<split>/<sha256>.png`` mask copies.

    Returns:
        Stats dict: ``exported``, ``skipped_degenerate``, ``per_split``
        (per split: count of accepted rows and exported samples), and
        ``accepted_missing`` (accepted rows without a valid split).

    Raises:
        FileNotFoundError: If a manifest row's frame file is absent
            (manifest and disk disagree: visible failure).
        RuntimeError: If a mask cannot be read (propagated from
            ``read_mask``).
    """
    images_dir = out_dir / "images"
    labels_dir = out_dir / "labels"
    for split in SPLITS:
        (images_dir / split).mkdir(parents=True, exist_ok=True)
        (labels_dir / split).mkdir(parents=True, exist_ok=True)
        (masks_out / split).mkdir(parents=True, exist_ok=True)
    stats: "dict[str, Any]" = {
        "exported": 0,
        "skipped_degenerate": 0,
        "accepted_missing": 0,
        "per_split": {split: {"exported": 0, "accepted": 0} for split in SPLITS},
    }
    for row in manifest_rows:
        accepted = str(row.get("accepted", ""))
        if accepted != "1":
            continue
        split = str(row.get("split", ""))
        if split not in SPLITS:
            stats["accepted_missing"] += 1
            continue
        stats["per_split"][split]["accepted"] += 1
        mask_path = labels_root / str(row["mask_relpath"])
        mask = read_mask(mask_path)
        mask_height, mask_width = mask.shape[:2]
        points = mask_to_polygon(mask, mask_width, mask_height)
        if points is None:
            stats["skipped_degenerate"] += 1
            continue
        sha = str(row["sha256"])
        shutil.copy2(
            originals / str(row["frame_relpath"]),
            images_dir / split / f"{sha}.jpg",
        )
        line = yolo_seg_line(points) + "\n"
        (labels_dir / split / f"{sha}.txt").write_text(line, encoding="utf-8")
        shutil.copy2(mask_path, masks_out / split / f"{sha}.png")
        stats["exported"] += 1
        stats["per_split"][split]["exported"] += 1

    yaml_text = (
        f"path: {out_dir.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "names:\n"
        "  0: plant\n"
    )
    (out_dir / "data.yaml").write_text(yaml_text, encoding="utf-8")
    return stats
