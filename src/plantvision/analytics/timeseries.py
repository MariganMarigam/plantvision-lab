"""Persistent per-frame time-series store for the P1 data flywheel.

Loads frame records (jpg + JSON sidecar) from the originals tree, measures
frames not yet present in the store (idempotent by the sidecar ``sha256``),
appends one CSV row per new frame, and regenerates the per-zone projected-area
plots from the full store.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2

from plantvision.analytics.plots import PlotPoint, plot_projected_area
from plantvision.vision.io import ImageReadError, load_image
from plantvision.vision.metrics import (
    FrameMeasurement,
    load_pipeline_config,
    measure_frame,
)

TIMESERIES_COLUMNS: tuple[str, ...] = (
    "sha256", "captured_at", "received_at", "camera_id", "zone_id", "width",
    "height", "px_per_mm", "area_px", "area_cm2", "roi_fraction_pct",
    "bbox_w", "bbox_h", "quality_flag", "scale_ok",
)

# Float columns -> decimal places in the store; None becomes "".
FLOAT_DECIMALS: dict[str, int] = {"px_per_mm": 4, "area_cm2": 3, "roi_fraction_pct": 3}


@dataclass(frozen=True)
class FrameRecord:
    """A frame to measure: jpg path plus the sidecar metadata used in rows."""

    jpg: Path
    sha256: str
    captured_at: str | None
    received_at: str | None
    camera_id: str
    zone_id: str
    width: int | None
    height: int | None


@dataclass(frozen=True)
class UpdateResult:
    """Summary of one :func:`run_update` pass."""

    scanned: int
    measured: int
    appended: int
    skipped: int
    errors: int
    rows_total: int
    plot_paths: tuple[Path, ...]


def _read_sidecar(sidecar: Path) -> dict | None:
    """Read a sidecar JSON; ``None`` when malformed/unreadable (caller skips)."""
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_frame_records(originals_dir: str | Path) -> list[FrameRecord]:
    """Load sidecar-backed frame records from an originals tree.

    Args:
        originals_dir: Root directory searched recursively for ``*.jpg``.

    Returns:
        Records sorted by ``(captured_at is None, captured_at, jpg name)`` —
        frames without a readable sidecar, without a ``sha256``, or with a
        malformed sidecar are skipped (never crash the scan).
    """
    records: list[FrameRecord] = []
    for p in sorted(Path(originals_dir).rglob("*.jpg")):
        sidecar = p.with_suffix(".json")
        if not sidecar.exists():
            continue
        meta = _read_sidecar(sidecar)
        if meta is None:
            continue
        sha = meta.get("sha256")
        if not (isinstance(sha, str) and sha):
            continue
        records.append(
            FrameRecord(
                jpg=p,
                sha256=sha,
                captured_at=meta.get("captured_at"),
                received_at=meta.get("received_at"),
                camera_id=str(meta.get("camera_id", "")),
                zone_id=str(meta.get("zone_id", "")),
                width=meta.get("width"),
                height=meta.get("height"),
            )
        )
    records.sort(key=lambda r: (r.captured_at is None, r.captured_at or "", r.jpg.name))
    return records


def read_timeseries(path: str | Path) -> list[dict[str, str]]:
    """Read the full store; missing file means an empty store.

    Args:
        path: Store CSV path.

    Returns:
        One dict per stored row (string values throughout).
    """
    p = Path(path)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def format_row(record: FrameRecord, meas: FrameMeasurement) -> dict[str, str]:
    """Convert a record + measurement into a TIMESERIES_COLUMNS-ordered row.

    Args:
        record: Sidecar-backed frame record (provenance columns).
        meas: Measurement from :func:`plantvision.vision.metrics.measure_frame`.

    Returns:
        String row; ``None`` float fields become ``""`` and ``scale_ok`` is
        ``true`` iff ``px_per_mm`` was detected.
    """

    def _fmt(value: float | None, decimals: int) -> str:
        return "" if value is None else f"{value:.{decimals}f}"

    return {
        "sha256": record.sha256,
        "captured_at": record.captured_at or "",
        "received_at": record.received_at or "",
        "camera_id": record.camera_id,
        "zone_id": record.zone_id,
        "width": "" if record.width is None else str(record.width),
        "height": "" if record.height is None else str(record.height),
        "px_per_mm": _fmt(meas.px_per_mm, FLOAT_DECIMALS["px_per_mm"]),
        "area_px": str(meas.projected_area_px),
        "area_cm2": _fmt(meas.projected_area_cm2, FLOAT_DECIMALS["area_cm2"]),
        "roi_fraction_pct": _fmt(meas.roi_fraction_pct, FLOAT_DECIMALS["roi_fraction_pct"]),
        "bbox_w": str(meas.bbox_w),
        "bbox_h": str(meas.bbox_h),
        "quality_flag": "|".join(meas.quality_flags),
        "scale_ok": "true" if meas.px_per_mm is not None else "false",
    }


def append_rows(path: str | Path, rows: Sequence[dict[str, str]]) -> int:
    """Append rows to the store, writing the header only when creating it.

    Args:
        path: Store CSV path (parent dirs created on first write).
        rows: String rows keyed by :data:`TIMESERIES_COLUMNS`.

    Returns:
        Number of rows appended (0 rows is a no-op that creates no file).

    Raises:
        OSError: If the store cannot be written.
    """
    if not rows:
        return 0
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    exists = p.exists() and p.stat().st_size > 0
    with p.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(TIMESERIES_COLUMNS))
        if not exists:
            writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def points_from_rows(rows: Sequence[dict[str, str]]) -> list[PlotPoint]:
    """Convert stored rows to plot points (bad floats degrade to unscaled)."""
    points: list[PlotPoint] = []
    for r in rows:
        cap = (r.get("captured_at") or "").strip()
        cm = (r.get("area_cm2") or "").strip()
        qf = (r.get("quality_flag") or "").strip()
        try:
            cmv: float | None = float(cm) if cm else None
        except ValueError:
            cmv = None
        points.append(
            PlotPoint(
                captured_at=cap or None,
                projected_area_cm2=cmv,
                quality_flags=tuple(qf.split("|")) if qf else (),
            )
        )
    return points


def run_update(
    originals_dir: str | Path, config_path: str | Path,
    store_path: str | Path, out_dir: str | Path,
) -> UpdateResult:
    """Measure every NEW frame and append it to the store, then re-plot.

    A frame is NEW iff its sidecar ``sha256`` is absent from the store; the
    scan is therefore idempotent (a second pass appends nothing). Undecodable
    jpgs increment ``errors`` and never abort the run. One plot per distinct
    ``zone_id`` is regenerated from the full store.

    Args:
        originals_dir: Root of the originals tree.
        config_path: Path to ``configs/pipeline.yaml``.
        store_path: Time-series CSV path.
        out_dir: Destination directory for the per-zone plots.

    Returns:
        An :class:`UpdateResult` summarizing the pass.

    Raises:
        FileNotFoundError, KeyError, ValueError: Propagated from
            :func:`load_pipeline_config` on a bad/missing config.
        OSError: Propagated from store/plot writes.
    """
    cfg = load_pipeline_config(config_path)
    records = load_frame_records(originals_dir)
    rows = read_timeseries(store_path)
    seen = {r.get("sha256", "") for r in rows}
    seen.discard("")

    measured = skipped = errors = 0
    new_rows: list[dict[str, str]] = []
    for rec in records:
        if rec.sha256 in seen:
            skipped += 1
            continue
        try:
            img = load_image(rec.jpg)
            meas, _mask = measure_frame(img, cfg)
        except (ImageReadError, ValueError, cv2.error):
            errors += 1
            continue
        new_rows.append(format_row(rec, meas))
        seen.add(rec.sha256)
        measured += 1

    appended = append_rows(store_path, new_rows)
    all_rows = rows + new_rows

    zones: dict[str, list[dict[str, str]]] = {}
    for r in all_rows:
        zones.setdefault(r.get("zone_id") or "unknown", []).append(r)
    plot_paths: list[Path] = []
    for zid in sorted(zones):
        slug = zid.replace("/", "_")
        out_png = Path(out_dir) / f"projected-area-{slug}.png"
        plot_projected_area(points_from_rows(zones[zid]), slug, cfg.pipeline_version, out_png)
        plot_paths.append(out_png)

    return UpdateResult(
        scanned=len(records),
        measured=measured,
        appended=appended,
        skipped=skipped,
        errors=errors,
        rows_total=len(all_rows),
        plot_paths=tuple(plot_paths),
    )
