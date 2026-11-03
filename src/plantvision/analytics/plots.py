"""Shared projected-area plotting (single renderer for report + flywheel)."""

from __future__ import annotations

import statistics
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


def _split_runs(
    points: Sequence[tuple[datetime, PlotPoint]],
    *,
    min_gap_hours: float = 2.0,
) -> list[list[tuple[datetime, PlotPoint]]]:
    """Split a chronological series where a capture gap exceeds the threshold.

    A break is inserted when ``dt - prev_dt`` exceeds
    ``max(3 * median_gap, min_gap_hours h)`` so a multi-hour hole is never
    drawn as an interpolated line.

    Args:
        points: Chronologically sorted ``(timestamp, point)`` pairs.
        min_gap_hours: Floor for the break threshold in hours.

    Returns:
        One list per continuous run; empty input yields an empty list.
    """
    if not points:
        return []
    if len(points) < 2:
        return [list(points)]
    gaps = [
        (current[0] - previous[0]).total_seconds()
        for previous, current in zip(points, points[1:])
    ]
    threshold = max(3.0 * statistics.median(gaps), min_gap_hours * 3600.0)
    runs: list[list[tuple[datetime, PlotPoint]]] = [[points[0]]]
    for previous, current in zip(points, points[1:]):
        if (current[0] - previous[0]).total_seconds() > threshold:
            runs.append([current])
        else:
            runs[-1].append(current)
    return runs


def plot_projected_area(
    points: Sequence[PlotPoint],
    zone: str,
    pipeline_version: str,
    out_png: Path,
    *,
    facecolor: str | None = None,
    ink: str | None = None,
) -> None:
    """Plot projected area (cm2) over capture time with failure-case markers.

    Green series: scaled frames. Small hollow red circles: quality-flagged
    frames (defects only — ``ok`` is not a flag). Red crosses at y=0: frames
    without a detectable marker (F1, unusable for cm2). Capture holes are drawn
    as breaks, never interpolated. The legend is built once from the actual
    artists, so split runs do not duplicate labels. The title is not drawn
    inside the image; the HTML figcaption is the only title.

    Args:
        points: One :class:`PlotPoint` per frame.
        zone: Zone label (kept for call-site compatibility; not drawn).
        pipeline_version: Pipeline label (kept for call-site compatibility;
            never drawn, so internal values do not leak into a chart title).
        out_png: Destination PNG path (parent dirs created).
        facecolor: Optional figure/axes background. ``None`` keeps the
            matplotlib default (white) and the legacy light output.
        ink: Optional axis/tick/label/legend colour. ``None`` keeps the
            matplotlib default (black).

    Raises:
        OSError: If the destination directory or PNG cannot be written.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    scaled = sorted(
        [(_parse_dt(p.captured_at), p) for p in points
         if p.projected_area_cm2 is not None and p.captured_at],
        key=lambda pair: pair[0],
    )
    unscaled = [p for p in points if p.projected_area_cm2 is None]
    unscaled_x = [_parse_dt(p.captured_at) for p in unscaled if p.captured_at]

    fig, ax = plt.subplots(figsize=(9, 3.2))
    if facecolor is not None:
        fig.patch.set_facecolor(facecolor)
        ax.set_facecolor(facecolor)
    handles: list[object] = []
    labels: list[str] = []
    if scaled:
        for index, run in enumerate(_split_runs(scaled)):
            xs = [dt for dt, _p in run]
            ys = [p.projected_area_cm2 for _dt, p in run]
            ax.plot(xs, ys, "-", color="#2e7d32", linewidth=1, zorder=1)
            # Split runs must not duplicate the legend label: only the first
            # run contributes a handle.
            artist = ax.scatter(
                xs, ys, s=40, color="#2e7d32",
                label="projected area (cm²)" if index == 0 else None,
                zorder=2,
            )
            if index == 0:
                handles.append(artist)
                labels.append("projected area (cm²)")
    flagged = [(dt, p) for dt, p in scaled if p.quality_flags]
    if flagged:
        artist = ax.scatter(
            [dt for dt, _p in flagged], [p.projected_area_cm2 for _dt, p in flagged],
            s=44, facecolors="none", edgecolors="#d32f2f", linewidths=0.8,
            label="quality flag (blur/dark/bright)", zorder=3,
        )
        handles.append(artist)
        labels.append("quality flag (blur/dark/bright)")
    if unscaled_x:
        artist = ax.scatter(
            unscaled_x, [0.0] * len(unscaled_x), marker="x", s=90, color="#d32f2f",
            label="no scale (unusable for cm²)", zorder=3,
        )
        handles.append(artist)
        labels.append("no scale (unusable for cm²)")
    ax.set_xlabel("captured_at (UTC)")
    ax.set_ylabel("projected area (cm²)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %H:%M"))
    if ink is not None:
        ax.tick_params(colors=ink)
        ax.xaxis.label.set_color(ink)
        ax.yaxis.label.set_color(ink)
        for spine in ax.spines.values():
            spine.set_color(ink)
        ax.grid(True, alpha=0.3, color=ink)
    else:
        ax.grid(True, alpha=0.3)
    if handles:
        legend = ax.legend(handles=handles, labels=labels, loc="best")
        if ink is not None:
            for text in legend.get_texts():
                text.set_color(ink)
    if scaled or unscaled_x:
        fig.autofmt_xdate(rotation=0, ha="center")
    if not scaled and not unscaled:
        ax.text(0.5, 0.5, "no frames", transform=ax.transAxes, ha="center")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    save_kwargs: dict[str, object] = {"dpi": 180}
    if facecolor is not None:
        save_kwargs["facecolor"] = facecolor
    fig.savefig(str(out_png), **save_kwargs)
    plt.close(fig)
