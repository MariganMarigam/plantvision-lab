"""Per-frame plant metrics: config dataclasses, measurement, aggregation (Stage 05).

Orchestrates segmentation, per-frame ArUco scale (ADR 0002: recomputed every
frame), and capture-quality scoring into a :class:`FrameMeasurement` per frame,
plus loading of frame/sidecar pairs from an originals tree.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np
import yaml

from plantvision.vision.io import load_image
from plantvision.vision.quality import blur_score, brightness_score, quality_flags
from plantvision.vision.scale import px_per_mm
from plantvision.vision.segmentation import segment_plant


@dataclass(frozen=True)
class SegmentationConfig:
    """Classic segmentation thresholds (mirrors ``configs/pipeline.yaml``)."""

    method: str = "hsv"
    hsv_lower: tuple[int, int, int] = (25, 40, 40)
    hsv_upper: tuple[int, int, int] = (95, 255, 255)
    exg_threshold: float = 20.0
    open_ksize: int = 5
    close_ksize: int = 7


@dataclass(frozen=True)
class QualityConfig:
    """Capture-quality gate thresholds."""

    blur_lapvar_min: float = 10.0
    brightness_min: float = 40.0
    brightness_max: float = 220.0


@dataclass(frozen=True)
class ScaleConfig:
    """ArUco scale-reference settings (per-frame calibration)."""

    aruco_dict: str = "DICT_5X5_50"
    marker_size_mm: float = 45.0


@dataclass(frozen=True)
class PipelineConfig:
    """Full CV pipeline configuration."""

    roi: tuple[int, int, int, int] | None
    segmentation: SegmentationConfig
    quality: QualityConfig
    scale: ScaleConfig
    pipeline_version: str


@dataclass(frozen=True)
class FrameRef:
    """A captured frame (jpg path + sidecar timestamp, if readable)."""

    jpg: Path
    captured_at: str | None


@dataclass(frozen=True)
class FrameMeasurement:
    """Metrics for one frame; ``None`` cm fields mean "no scale" (F1)."""

    stem: str
    captured_at: str | None
    px_per_mm: float | None
    projected_area_px: int
    projected_area_cm2: float | None
    roi_fraction_pct: float
    bbox_w: int
    bbox_h: int
    bbox_w_cm: float | None
    bbox_h_cm: float | None
    blur_lapvar: float
    brightness_mean: float
    quality_flags: tuple[str, ...]

    def as_row(self) -> dict:
        """Flat dict for CSV rows; quality flags joined with ``|``."""
        return {
            "stem": self.stem,
            "captured_at": self.captured_at,
            "px_per_mm": self.px_per_mm,
            "projected_area_px": self.projected_area_px,
            "projected_area_cm2": self.projected_area_cm2,
            "roi_fraction_pct": self.roi_fraction_pct,
            "bbox_w": self.bbox_w,
            "bbox_h": self.bbox_h,
            "bbox_w_cm": self.bbox_w_cm,
            "bbox_h_cm": self.bbox_h_cm,
            "blur_lapvar": self.blur_lapvar,
            "brightness_mean": self.brightness_mean,
            "quality_flags": "|".join(self.quality_flags),
        }


def load_pipeline_config(path: str | Path) -> PipelineConfig:
    """Load ``configs/pipeline.yaml`` into typed config dataclasses.

    Args:
        path: Path to the pipeline YAML file.

    Returns:
        Parsed :class:`PipelineConfig`.

    Raises:
        KeyError: If a required key (``roi``, ``scale_reference``,
            ``pipeline_version``) is missing.
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    roi = tuple(raw["roi"]) if raw.get("roi") else None
    sr = raw["scale_reference"]
    scale = ScaleConfig(aruco_dict=sr["dict"], marker_size_mm=float(sr["marker_size_mm"]))
    sg = raw.get("segmentation", {})
    segmentation = SegmentationConfig(
        method=sg.get("method", "hsv"),
        hsv_lower=tuple(sg.get("hsv_lower", (25, 40, 40))),
        hsv_upper=tuple(sg.get("hsv_upper", (95, 255, 255))),
        exg_threshold=float(sg.get("exg_threshold", 20.0)),
        open_ksize=int(sg.get("open_ksize", 5)),
        close_ksize=int(sg.get("close_ksize", 7)),
    )
    q = raw.get("quality", {})
    quality = QualityConfig(
        blur_lapvar_min=float(q.get("blur_lapvar_min", 10.0)),
        brightness_min=float(q.get("brightness_min", 40.0)),
        brightness_max=float(q.get("brightness_max", 220.0)),
    )
    return PipelineConfig(
        roi=roi,
        segmentation=segmentation,
        quality=quality,
        scale=scale,
        pipeline_version=str(raw["pipeline_version"]),
    )


def _apply_roi(img: np.ndarray, roi: tuple[int, int, int, int] | None) -> np.ndarray:
    """Clamp and apply the ROI crop; full image when ``roi`` is None.

    Args:
        img: BGR uint8 image.
        roi: ``(x, y, w, h)`` pixels or ``None``.

    Returns:
        The (possibly cropped) image.

    Raises:
        ValueError: If the ROI lies entirely outside the image.
    """
    if roi is None:
        return img
    x, y, w, h = roi
    x = max(0, x)
    y = max(0, y)
    w = min(w, img.shape[1] - x)
    h = min(h, img.shape[0] - y)
    if w <= 0 or h <= 0:
        raise ValueError("roi is outside the image")
    return img[y:y + h, x:x + w]


def _cm_metrics(
    area_px: int, bw: int, bh: int, ppm: float | None
) -> tuple[float | None, float | None, float | None]:
    """Convert pixel metrics to cm using the frame's px/mm (None when unscaled).

    Args:
        area_px: Projected area in pixels.
        bw: Bounding-box width in pixels.
        bh: Bounding-box height in pixels.
        ppm: Pixels per millimeter, or ``None`` when no marker was found.

    Returns:
        ``(projected_area_cm2, bbox_w_cm, bbox_h_cm)``; all None if unscaled.
    """
    if ppm is None:
        return None, None, None
    return area_px / (ppm**2) / 100.0, bw / ppm / 10.0, bh / ppm / 10.0


def measure_frame(
    img: np.ndarray, cfg: PipelineConfig
) -> tuple[FrameMeasurement, np.ndarray]:
    """Measure one BGR frame: segmentation, scale, quality flags.

    Args:
        img: BGR uint8 image with shape ``(H, W, 3)``.
        cfg: Parsed pipeline configuration.

    Returns:
        ``(FrameMeasurement, mask)`` where mask is the ``(H, W)`` uint8 plant
        mask of the (possibly ROI-cropped) image. Scale is computed on the
        full frame even when an ROI crop is applied.

    Raises:
        ValueError: If ``img`` is not 3-channel or the ROI is invalid.
    """
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError(f"expected (H, W, 3) BGR image, got shape={img.shape}")
    crop = _apply_roi(img, cfg.roi)
    mask = segment_plant(
        crop,
        method=cfg.segmentation.method,
        hsv_lower=cfg.segmentation.hsv_lower,
        hsv_upper=cfg.segmentation.hsv_upper,
        exg_threshold=cfg.segmentation.exg_threshold,
        open_ksize=cfg.segmentation.open_ksize,
        close_ksize=cfg.segmentation.close_ksize,
    )
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    flags = quality_flags(
        gray, cfg.quality.blur_lapvar_min, cfg.quality.brightness_min, cfg.quality.brightness_max
    )
    area_px = int(cv2.countNonZero(mask))
    if area_px > 0:
        _, _, bw, bh = cv2.boundingRect(mask)
    else:
        bw = bh = 0
    h_px, w_px = mask.shape[0], mask.shape[1]
    roi_fraction_pct = 100.0 * area_px / float(h_px * w_px)
    ppm = px_per_mm(img, cfg.scale.marker_size_mm, cfg.scale.aruco_dict)
    area_cm2, bbox_w_cm, bbox_h_cm = _cm_metrics(area_px, bw, bh, ppm)
    measurement = FrameMeasurement(
        stem="",
        captured_at=None,
        px_per_mm=ppm,
        projected_area_px=area_px,
        projected_area_cm2=area_cm2,
        roi_fraction_pct=roi_fraction_pct,
        bbox_w=bw,
        bbox_h=bh,
        bbox_w_cm=bbox_w_cm,
        bbox_h_cm=bbox_h_cm,
        blur_lapvar=blur_score(gray),
        brightness_mean=brightness_score(gray),
        quality_flags=tuple(flags),
    )
    return measurement, mask


def load_frames(originals_dir: str | Path) -> list[FrameRef]:
    """Pair every ``*.jpg`` under ``originals_dir`` with its ``.json`` sidecar.

    Args:
        originals_dir: Root directory searched recursively for frames.

    Returns:
        Frame refs sorted chronologically (unknown timestamps last). Frames
        without a sidecar are skipped; malformed sidecars yield
        ``captured_at=None`` without crashing.
    """
    refs: list[FrameRef] = []
    for p in sorted(Path(originals_dir).rglob("*.jpg")):
        sidecar = p.with_suffix(".json")
        if not sidecar.exists():
            continue
        captured_at: str | None = None
        try:
            captured_at = json.loads(sidecar.read_text(encoding="utf-8")).get("captured_at")
        except (json.JSONDecodeError, OSError):
            captured_at = None
        refs.append(FrameRef(jpg=p, captured_at=captured_at))
    refs.sort(key=lambda r: (r.captured_at is None, r.captured_at or "", r.jpg.name))
    return refs


def measure_frames(
    refs: Sequence[FrameRef], cfg: PipelineConfig
) -> list[tuple[FrameRef, FrameMeasurement, np.ndarray]]:
    """Measure a sequence of frame refs.

    Args:
        refs: Frame refs (as produced by :func:`load_frames`).
        cfg: Parsed pipeline configuration.

    Returns:
        Aligned ``(ref, measurement, mask)`` triples, input order preserved.

    Raises:
        plantvision.vision.io.ImageReadError: If a jpg cannot be decoded.
    """
    out: list[tuple[FrameRef, FrameMeasurement, np.ndarray]] = []
    for ref in refs:
        img = load_image(ref.jpg)
        meas, mask = measure_frame(img, cfg)
        meas = dataclasses.replace(meas, stem=ref.jpg.stem, captured_at=ref.captured_at)
        out.append((ref, meas, mask))
    return out
