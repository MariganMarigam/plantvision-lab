"""Batch measurement runner for a capture series (Stage 05).

Processes every frame (``jpg`` + ``json`` sidecar) under ``--originals`` with
the configured pipeline, writes one mask PNG per frame mirroring the originals
tree, a per-frame metrics CSV, a projected-area plot over capture time (with
no-scale and quality-flag markers), and ``run_summary.md`` reproducing the
known Stage 05 failure cases.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import cv2

from plantvision.vision.metrics import (
    FrameMeasurement,
    load_frames,
    load_pipeline_config,
    measure_frames,
)

HEADER = [
    "stem", "captured_at", "px_per_mm", "projected_area_px", "projected_area_cm2",
    "roi_fraction_pct", "bbox_w", "bbox_h", "bbox_w_cm", "bbox_h_cm",
    "blur_lapvar", "brightness_mean", "quality_flags",
]

# Float fields -> decimal places in the CSV; None becomes "".
_FLOAT_FMT = {
    "px_per_mm": 4,
    "projected_area_cm2": 3,
    "roi_fraction_pct": 3,
    "bbox_w_cm": 4,
    "bbox_h_cm": 4,
    "blur_lapvar": 2,
    "brightness_mean": 2,
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments (all with plan defaults)."""
    parser = argparse.ArgumentParser(description="Measure a capture series (Stage 05).")
    parser.add_argument("--originals", default="data/originals")
    parser.add_argument("--config", default="configs/pipeline.yaml")
    parser.add_argument("--masks", default="data/masks")
    parser.add_argument("--out", default="data/derived/plots")
    parser.add_argument("--zone", default="shelf-a_tray-1")
    return parser.parse_args(argv)


def _parse_dt(captured_at: str) -> datetime:
    """Parse an ISO timestamp, tolerating a trailing ``Z``."""
    return datetime.fromisoformat(captured_at.replace("Z", "+00:00"))


def _format_row(meas: FrameMeasurement) -> dict:
    """Convert a measurement into a HEADER-ordered row of CSV strings."""
    row = meas.as_row()
    for key, decimals in _FLOAT_FMT.items():
        value = row[key]
        row[key] = "" if value is None else f"{value:.{decimals}f}"
    return row


def write_csv(rows: list[dict], path: Path) -> None:
    """Write pre-formatted string rows to a CSV file.

    Args:
        rows: Rows as produced by :func:`_format_row` (strings throughout).
        path: Destination CSV path (parent dirs created).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)


def write_masks(items: list, originals_dir: Path, masks_dir: Path) -> int:
    """Write one mask PNG per measured frame, mirroring the originals layout.

    Args:
        items: ``(ref, measurement, mask)`` triples from ``measure_frames``.
        originals_dir: Root of the originals tree (for relative paths).
        masks_dir: Destination root for the mask tree.

    Returns:
        Number of masks written.

    Raises:
        OSError: If ``cv2.imwrite`` fails for any mask.
    """
    written = 0
    for ref, _meas, mask in items:
        rel = ref.jpg.relative_to(originals_dir)
        dest = masks_dir / rel.with_suffix(".png")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(dest), mask):
            raise OSError(f"cannot write mask: {dest}")
        written += 1
    return written


def plot_series(
    measurements: list[FrameMeasurement], zone: str, pipeline_version: str, out_png: Path
) -> None:
    """Plot projected area (cm2) over capture time with failure-case markers.

    Green series: scaled frames. Red circles: quality-flagged frames. Red
    crosses at y=0: frames without a detectable marker (F1, unusable for cm2).

    Args:
        measurements: One :class:`FrameMeasurement` per frame.
        zone: Zone label for the title.
        pipeline_version: Pipeline version for the title.
        out_png: Destination PNG path (parent dirs created).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scaled = sorted(
        [(_parse_dt(m.captured_at), m) for m in measurements
         if m.projected_area_cm2 is not None and m.captured_at],
        key=lambda pair: pair[0],
    )
    unscaled = [m for m in measurements if m.projected_area_cm2 is None]
    unscaled_x = [_parse_dt(m.captured_at) for m in unscaled if m.captured_at]

    fig, ax = plt.subplots(figsize=(12, 6))
    if scaled:
        xs = [dt for dt, _m in scaled]
        ys = [m.projected_area_cm2 for _dt, m in scaled]
        ax.plot(xs, ys, "-", color="#2e7d32", linewidth=1, zorder=1)
        ax.scatter(xs, ys, s=40, color="#2e7d32", label="projected area (cm²)", zorder=2)
    flagged = [(dt, m) for dt, m in scaled if m.quality_flags]
    if flagged:
        ax.scatter(
            [dt for dt, _m in flagged], [m.projected_area_cm2 for _dt, m in flagged],
            s=140, facecolors="none", edgecolors="#d32f2f", linewidths=1.5,
            label="quality flag (blur/dark/bright)", zorder=3,
        )
    if unscaled_x:
        ax.scatter(
            unscaled_x, [0.0] * len(unscaled_x), marker="x", s=90, color="#d32f2f",
            label="no scale (unusable for cm²)", zorder=3,
        )
    ax.set_xlabel("captured_at (UTC)")
    ax.set_ylabel("projected area (cm²)")
    ax.set_title(f"PlantVision Stage 05 — {zone} — pipeline {pipeline_version}")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    if scaled or unscaled_x:
        fig.autofmt_xdate()
    if not scaled and not unscaled:
        ax.text(0.5, 0.5, "no frames", transform=ax.transAxes, ha="center")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(str(out_png), dpi=150)
    plt.close(fig)


def write_summary(
    measurements: list[FrameMeasurement], zone: str, pipeline_version: str, out_md: Path
) -> None:
    """Write ``run_summary.md``: counts, F1 unscaled frames, flags, ranges.

    Args:
        measurements: One :class:`FrameMeasurement` per frame.
        zone: Zone label for the header.
        pipeline_version: Pipeline version for the header.
        out_md: Destination markdown path (parent dirs created).
    """
    scaled = [m for m in measurements if m.px_per_mm is not None]
    unscaled = [m for m in measurements if m.px_per_mm is None]
    flagged = [m for m in measurements if m.quality_flags]
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# PlantVision Stage 05 run summary — {zone}",
        "",
        f"- pipeline_version: `{pipeline_version}`",
        f"- generated_at: {generated_at}",
        f"- frames total: {len(measurements)}",
        f"- scaled (cm² available): {len(scaled)}",
        f"- unscaled (no scale): {len(unscaled)}",
        "",
        "## Unscaled frames (no scale — F1)",
        "",
    ]
    if unscaled:
        lines += [f"- {m.stem} ({m.captured_at})" for m in unscaled]
    else:
        lines.append("- none")
    lines += ["", "## Quality-flagged frames", ""]
    if flagged:
        lines += [f"- {m.stem}: {'|'.join(m.quality_flags)}" for m in flagged]
    else:
        lines.append("- none")
    lines += ["", "## Ranges over scaled frames", ""]
    if scaled:
        lines += [
            f"- px_per_mm: {min(m.px_per_mm for m in scaled):.4f}"
            f" – {max(m.px_per_mm for m in scaled):.4f}",
            f"- projected_area_cm2: {min(m.projected_area_cm2 for m in scaled):.3f}"
            f" – {max(m.projected_area_cm2 for m in scaled):.3f}",
        ]
    else:
        lines.append("- n/a (no scaled frames)")
    lines += [
        "",
        "## Known Stage 05 failure cases (documented, not fixed here)",
        "",
        "- F2 near-empty mask: the starting HSV band can be too strict for some",
        "  lighting/framing, producing a tiny/zero projected area despite a plant",
        "  in frame (2026-10-16: …b14c6f green 0.032, …e6965e green 0.035).",
        "- F3 low-texture is not blur: recent frames (Laplacian variance ≈ 16–17)",
        "  are a low-texture scene (small plant, flat shelf); blur_lapvar_min=10.0",
        "  deliberately does not flag them. Re-tune in Stage 08 with labelled blur.",
        "- Occlusion/overlap: a leaf over the plant lowers projected area.",
    ]
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the batch measurement; returns 0, or 1 when no frames are found.

    Args:
        argv: CLI arguments (defaults per :func:`parse_args` when None).

    Returns:
        0 on success; 1 only when no frames (jpg+sidecar pairs) were found.
    """
    args = parse_args(argv)
    cfg = load_pipeline_config(args.config)
    refs = load_frames(args.originals)
    if not refs:
        print("measure_series: no frames found")
        return 1
    items = measure_frames(refs, cfg)
    n_masks = write_masks(items, Path(args.originals), Path(args.masks))
    rows = [_format_row(m) for _ref, m, _mask in items]
    csv_path = Path(args.out) / f"projected-area-{args.zone}.csv"
    png_path = Path(args.out) / f"projected-area-{args.zone}.png"
    write_csv(rows, csv_path)
    plot_series([m for _ref, m, _mask in items], args.zone, cfg.pipeline_version, png_path)
    write_summary(
        [m for _ref, m, _mask in items], args.zone, cfg.pipeline_version,
        Path(args.out) / "run_summary.md",
    )
    print(f"measure_series: {len(items)} frames, {n_masks} masks -> {csv_path}, {png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
