"""Shared projected-area plotting (single renderer for report + flywheel)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class PlotPoint:
    """One plottable frame: timestamp, scaled area, quality flags."""

    captured_at: str | None
    projected_area_cm2: float | None
    quality_flags: tuple[str, ...]


def _parse_dt(captured_at: str) -> datetime:
    """Parse an ISO timestamp, tolerating a trailing ``Z``."""
    return datetime.fromisoformat(captured_at.replace("Z", "+00:00"))


def plot_projected_area(
    points: Sequence[PlotPoint], zone: str, pipeline_version: str, out_png: Path
) -> None:
    """Plot projected area (cm2) over capture time with failure-case markers.

    Green series: scaled frames. Red circles: quality-flagged frames. Red
    crosses at y=0: frames without a detectable marker (F1, unusable for cm2).

    Args:
        points: One :class:`PlotPoint` per frame.
        zone: Zone label for the title.
        pipeline_version: Pipeline version for the title.
        out_png: Destination PNG path (parent dirs created).

    Raises:
        OSError: If the destination directory or PNG cannot be written.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scaled = sorted(
        [(_parse_dt(p.captured_at), p) for p in points
         if p.projected_area_cm2 is not None and p.captured_at],
        key=lambda pair: pair[0],
    )
    unscaled = [p for p in points if p.projected_area_cm2 is None]
    unscaled_x = [_parse_dt(p.captured_at) for p in unscaled if p.captured_at]

    fig, ax = plt.subplots(figsize=(12, 6))
    if scaled:
        xs = [dt for dt, _p in scaled]
        ys = [p.projected_area_cm2 for _dt, p in scaled]
        ax.plot(xs, ys, "-", color="#2e7d32", linewidth=1, zorder=1)
        ax.scatter(xs, ys, s=40, color="#2e7d32", label="projected area (cm²)", zorder=2)
    flagged = [(dt, p) for dt, p in scaled if p.quality_flags]
    if flagged:
        ax.scatter(
            [dt for dt, _p in flagged], [p.projected_area_cm2 for _dt, p in flagged],
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
