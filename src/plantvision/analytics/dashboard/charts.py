"""Twelve pure-string SVG chart primitives (no data loading, no HTML shell).

Geometry is fixed by the v2 plan: 720x240 cartesian plots with a 44/18/18/40
padding box, 658x182 plot rect, unsmoothed polylines split at capture gaps and
gradient/hatch definitions repeated in every cartesian chart so a cloned SVG
in the drawer never references a missing id.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from .svg import (
    chart_close,
    chart_open,
    defs_band,
    defs_gradient,
    defs_hatch,
    esc,
    fmt_value,
    linear,
    nice_ticks,
    num,
    path_polyline,
    text,
)

PAD_L, PAD_R, PAD_T, PAD_B = 44, 18, 18, 40
PLOT_W = 658
PLOT_H = 182
Y_LABEL_X = PAD_L - 6
X_LABEL_Y = PAD_T + PLOT_H + 26
X_TITLE_Y = PAD_T + PLOT_H + 38
LEGEND_Y = PAD_T + PLOT_H + 58


@dataclass(frozen=True)
class ChartSpec:
    """Identity and formatting for one chart node."""

    chart_id: str
    title: str
    desc: str
    unit: str = ""
    decimals: int = 1


@dataclass(frozen=True)
class PlotSeries:
    """One legend entry: slot A/B/C plus its (possibly split) runs."""

    slot: str
    runs: Sequence[Sequence[tuple[int, float]]]
    label: str = ""


@dataclass(frozen=True)
class Band:
    """A shaded corridor between two y values."""

    lo: float
    hi: float
    kind: str = "warn"


@dataclass(frozen=True)
class Threshold:
    """A dashed horizontal threshold line."""

    value: float
    label: str
    kind: str = "warn"


@dataclass(frozen=True)
class BarItem:
    """One bar; ``None`` means not measured."""

    label: str
    value: float | None
    kind: str = "ok"
    note: str = ""


@dataclass(frozen=True)
class StackItem:
    """A measured/total column."""

    label: str
    measured: float
    total: float


@dataclass(frozen=True)
class StripRow:
    """One segment strip row."""

    label: str
    cells: Sequence[float | None]
    off: bool = False


@dataclass(frozen=True)
class CalendarRow:
    """One calendar row: ``(UTC date, frame count)`` cells."""

    label: str
    cells: Sequence[tuple[str, int]]


@dataclass(frozen=True)
class BoxGroup:
    """Five-number summary for one box."""

    label: str
    lo: float
    q1: float
    median: float
    q3: float
    hi: float


@dataclass(frozen=True)
class DonutSegment:
    """One donut slice."""

    label: str
    value: float
    kind: str = "ok"


@dataclass(frozen=True)
class RadarSeries:
    """One radar polygon; values are normalised to ``0..1``."""

    label: str
    values: Sequence[float]
    slot: str = "A"


_BAND_COLOUR = {
    "warn": "#FBC490",
    "critical": "#F5705E",
    "ok": "#2FE3A7",
}
_RAMP = ("#453E77", "#8A5F86", "#BF7C8B", "#E59B8B", "#FBC490")
_SLOT_FILL = {
    "A": "url(#pv-grad-a)",
    "B": "url(#pv-hatch-b)",
    "C": "var(--pv-pos)",
}
_SLOT_STROKE = {
    "A": "url(#pv-grad-a)",
    "B": "url(#pv-grad-b)",
    "C": "var(--pv-pos)",
}
_SLOT_DASH = {"A": "", "B": ' stroke-dasharray="6 4"', "C": ' stroke-dasharray="1 3"'}
_SLOT_KIND = {"A": "ok", "B": "warn", "C": "ok"}
# Swatches use resolved colours, not url(#...): a horizontal <line> has a
# zero-height gradient bounding box and loses the paint when a chart is cloned
# into the drawer without its <defs>.
_SLOT_SWATCH_STROKE = {
    "A": "#F5705E",
    "B": "#C159F5",
    "C": "var(--pv-pos)",
}


def _defs() -> str:
    """Shared gradient, band and hatch definitions for every cartesian chart."""
    return _DEFS


_DEFS = (
    "<defs>"
    + defs_gradient("pv-grad-a", (("0%", "#F5705E"), ("100%", "#FBC490")))
    + '<linearGradient id="pv-grad-a-fill" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0%" stop-color="#F5705E" stop-opacity="0.35"/>'
    '<stop offset="100%" stop-color="#FBC490" stop-opacity="0"/>'
    "</linearGradient>"
    + defs_gradient("pv-grad-b", (("0%", "#C159F5"), ("100%", "#7B3FE0")))
    + defs_band("pv-band-warn", _BAND_COLOUR["warn"])
    + defs_band("pv-band-critical", _BAND_COLOUR["critical"])
    + defs_band("pv-band-ok", _BAND_COLOUR["ok"])
    + defs_hatch("pv-hatch-b", "#C159F5")
    + "</defs>"
)


def chart_defs() -> str:
    """Return the shared ``<defs>`` block for the page-level SVG.

    Every cartesian primitive also embeds this block when rendered standalone;
    the page keeps exactly one copy so ids stay unique.
    """
    return _DEFS


def not_measured_panel(spec: ChartSpec, reason: str) -> str:
    """Render the panel-level empty state (never a fake zero).

    Args:
        spec: Chart identity.
        reason: Human reason shown under the title.

    Returns:
        The empty-state markup.
    """
    return (
        '<div class="pv-empty" role="note" data-state="not-measured">'
        f'<p class="pv-empty-t">{esc(spec.title)}</p><p>{esc(reason)}</p></div>'
    )


def _y_domain(values: Sequence[float], *, floor_zero: bool = False) -> tuple[float, float]:
    """Padded y domain for a set of finite values."""
    if not values:
        return 0.0, 1.0
    lo, hi = min(values), max(values)
    if floor_zero:
        lo, hi = min(lo, 0.0), max(hi, 0.0)
    span = hi - lo
    pad = 1.0 if span == 0 else span * 0.07
    return lo - pad, hi + pad


def _x_domain(runs: Sequence[Sequence[tuple[int, float]]]) -> tuple[int, int]:
    """Padded epoch-ms x domain across every run."""
    xs = [point[0] for run in runs for point in run]
    if not xs:
        return 0, 1
    lo, hi = min(xs), max(xs)
    if lo == hi:
        return lo - 3_600_000, hi + 3_600_000
    return lo, hi


def _time_label(timestamp_ms: float, *, hours_span: float) -> str:
    """Format an axis tick as ``%H:%M`` under 48 h, else ``%d %b``."""
    moment = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
    return moment.strftime("%H:%M" if hours_span < 48.0 else "%d %b")


def _axes(
    *,
    x_lo: float,
    x_hi: float,
    y_lo: float,
    y_hi: float,
    width: int,
) -> str:
    """Grid, y labels, x labels and axis titles for a cartesian plot."""
    y_scale = linear((y_lo, y_hi), (PAD_T + PLOT_H, PAD_T))
    x_scale = linear((x_lo, x_hi), (PAD_L, PAD_L + PLOT_W))
    tick_decimals = 0 if y_hi >= 10.0 else 2
    parts: list[str] = []
    ticks, _step = nice_ticks(y_lo, y_hi, 4)
    for tick in ticks:
        y = y_scale(tick)
        parts.append(
            f'<line x1="{PAD_L}" y1="{num(y)}" x2="{PAD_L + PLOT_W}" '
            f'y2="{num(y)}" stroke="var(--pv-grid)" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{Y_LABEL_X}" y="{num(y)}" class="pv-ax" text-anchor="end" '
            f'dominant-baseline="middle">{esc(num(tick, tick_decimals))}</text>'
        )
    hours_span = (x_hi - x_lo) / 3_600_000.0
    if x_hi > x_lo:
        for index in range(6):
            timestamp = x_lo + (x_hi - x_lo) * index / 5.0
            x = x_scale(timestamp)
            if 0 < index < 5:
                parts.append(
                    f'<line x1="{num(x)}" y1="{PAD_T}" x2="{num(x)}" '
                    f'y2="{PAD_T + PLOT_H}" stroke="var(--pv-grid)" stroke-width="1"/>'
                )
            parts.append(
                f'<text x="{num(x)}" y="{X_LABEL_Y}" class="pv-ax" '
                f'text-anchor="middle">{esc(_time_label(timestamp, hours_span=hours_span))}'
                "</text>"
            )
    parts.append(
        text(PAD_L + PLOT_W / 2, X_TITLE_Y, "captured_at (UTC)", anchor="middle")
    )
    return "".join(parts)


def _band_rect(band: Band, y_scale: object, y_lo: float, y_hi: float) -> str:
    """One shaded corridor, clipped to the y domain."""
    lo, hi = (band.lo, band.hi) if band.lo <= band.hi else (band.hi, band.lo)
    lo = max(lo, y_lo)
    hi = min(hi, y_hi)
    if hi < lo:
        lo = hi
    top = y_scale(hi)  # type: ignore[operator]
    bottom = y_scale(lo)  # type: ignore[operator]
    return (
        f'<rect class="pv-band" x="{PAD_L}" width="{PLOT_W}" y="{num(top)}" '
        f'height="{num(max(0.0, bottom - top))}" fill="url(#pv-band-{esc(band.kind)})"'
        "/>"
    )


def _threshold_line(
    threshold: Threshold, y_scale: object, y_lo: float, y_hi: float
) -> str:
    """One dashed threshold line with its right-aligned label."""
    if not (y_lo <= threshold.value <= y_hi):
        return ""
    y = y_scale(threshold.value)  # type: ignore[operator]
    dash = "4 3" if threshold.kind == "warn" else "2 2"
    colour = _BAND_COLOUR.get(threshold.kind, _BAND_COLOUR["warn"])
    return (
        f'<line class="pv-threshold" x1="{PAD_L}" x2="{PAD_L + PLOT_W}" '
        f'y1="{num(y)}" y2="{num(y)}" stroke="{colour}" stroke-dasharray="{dash}"/>'
        f'<text x="700" y="{num(y - 4)}" class="pv-ax" text-anchor="end">'
        f"{esc(threshold.label)}</text>"
    )


def line_chart(
    spec: ChartSpec,
    series: Sequence[PlotSeries],
    *,
    bands: Sequence[Band] = (),
    thresholds: Sequence[Threshold] = (),
    missing: Sequence[int] = (),
    width: int = 720,
    height: int = 240,
    y_floor_zero: bool = False,
) -> str:
    """Gap-aware multi-series line chart.

    Args:
        spec: Chart identity/formatting.
        series: One entry per panel; slot A/B/C controls the style.
        bands: Shaded corridors drawn under the lines.
        thresholds: Dashed horizontal threshold lines.
        missing: Epoch-ms positions marked with a small ``×`` on the baseline.
        width: ViewBox width.
        height: ViewBox height.
        y_floor_zero: Include zero in the y domain.

    Returns:
        The chart markup, or the not-measured panel.

    Raises:
        ValueError: If the chart is smaller than 120x80.
    """
    if width < 120 or height < 80:
        raise ValueError(f"chart too small: {width}x{height}")
    if not series or not any(item.runs for item in series):
        return not_measured_panel(spec, "no numeric points in this store")
    values = [point[1] for item in series for run in item.runs for point in run]
    all_runs = [run for item in series for run in item.runs]
    drawable = [item for item in series if any(item.runs)]
    multi = len(drawable) > 1
    chart_height = height + (26 if multi else 0)
    y_lo, y_hi = _y_domain(values, floor_zero=y_floor_zero)
    x_lo, x_hi = _x_domain(all_runs)
    y_scale = linear((y_lo, y_hi), (PAD_T + PLOT_H, PAD_T))
    x_scale = linear((x_lo, x_hi), (PAD_L, PAD_L + PLOT_W))
    parts = [
        chart_open(
            width,
            chart_height,
            chart_id=spec.chart_id,
            title=spec.title,
            desc=spec.desc,
        ),
        _defs(),
        _axes(x_lo=x_lo, x_hi=x_hi, y_lo=y_lo, y_hi=y_hi, width=width),
    ]
    parts.extend(_band_rect(band, y_scale, y_lo, y_hi) for band in bands)
    parts.extend(
        _threshold_line(threshold, y_scale, y_lo, y_hi) for threshold in thresholds
    )
    total_points = len(values)
    for series_index, item in enumerate(series):
        slot = item.slot if item.slot in _SLOT_STROKE else "A"
        dash = _SLOT_DASH[slot]
        stroke = _SLOT_STROKE[slot]
        parts.append(f'<g data-series="{slot}" data-label="{esc(item.label)}">')
        for run_index, run in enumerate(item.runs):
            if len(run) < 2:
                continue
            points = [(x_scale(point[0]), y_scale(point[1])) for point in run]
            parts.append(
                f'<path class="pv-line pv-draw" d="{path_polyline(points)}" '
                f'fill="none" stroke="{stroke}" stroke-width="2" '
                f'stroke-linejoin="round" vector-effect="non-scaling-stroke" '
                f'pathLength="1"{dash} data-run="{run_index}"/>'
            )
        for run in item.runs:
            for point in run:
                parts.append(
                    f'<circle cx="{num(x_scale(point[0]))}" '
                    f'cy="{num(y_scale(point[1]))}" r="1.9" fill="{stroke}"/>'
                )
        if item.runs and not multi:
            last = item.runs[-1][-1]
            parts.append(
                f'<text x="700" y="{30 + series_index * 14}" class="pv-last" '
                f'text-anchor="end">{esc(fmt_value(last[1], spec.decimals, spec.unit))}'
                "</text>"
            )
        parts.append("</g>")
    if multi:
        parts.append(_series_legend(drawable, spec))
    if total_points > 0:
        for timestamp in missing:
            clamped = min(max(float(timestamp), x_lo), x_hi)
            x = x_scale(clamped)
            y = PAD_T + PLOT_H - 6
            parts.append(
                f'<path class="pv-miss" d="M{num(x - 3)} {y} l6 6 '
                f'M{num(x + 3)} {y} l-6 6" stroke="var(--pv-neg)" '
                'stroke-width="1.6" fill="none"/>'
            )
    parts.append(chart_close())
    return "".join(parts)


def _series_legend(series: Sequence[PlotSeries], spec: ChartSpec) -> str:
    """One legend row under a multi-series chart: swatch, name, last value."""
    if not series:
        return ""
    slot_width = PLOT_W / len(series)
    parts = ['<g class="pv-series-legend">']
    for index, item in enumerate(series):
        x = PAD_L + index * slot_width
        slot = item.slot if item.slot in _SLOT_STROKE else "A"
        parts.append(
            f'<line class="pv-swatch" x1="{num(x)}" y1="{num(LEGEND_Y)}" '
            f'x2="{num(x + 16)}" y2="{num(LEGEND_Y)}" '
            f'stroke="{_SLOT_SWATCH_STROKE[slot]}" stroke-width="3" '
            f'stroke-linecap="round"{_SLOT_DASH[slot]}/>'
        )
        last = item.runs[-1][-1]
        label = item.label or slot
        limit = max(4, int((slot_width - 30) / 6.2))
        if len(label) > limit:
            label = label[:limit - 1] + "…"
        value = f"{num(last[1], spec.decimals)} {spec.unit}".strip()
        parts.append(text(x + 22, LEGEND_Y + 4, f"{label} · {value}", cls="pv-legend"))
    parts.append("</g>")
    return "".join(parts)


def area_chart(
    spec: ChartSpec,
    runs: Sequence[Sequence[tuple[int, float]]],
    *,
    width: int = 720,
    height: int = 240,
) -> str:
    """Single-series area chart with the same axes as :func:`line_chart`."""
    if width < 120 or height < 80:
        raise ValueError(f"chart too small: {width}x{height}")
    if not runs or not any(runs):
        return not_measured_panel(spec, "no numeric points in this store")
    values = [point[1] for run in runs for point in run]
    y_lo, y_hi = _y_domain(values, floor_zero=True)
    x_lo, x_hi = _x_domain(runs)
    y_scale = linear((y_lo, y_hi), (PAD_T + PLOT_H, PAD_T))
    x_scale = linear((x_lo, x_hi), (PAD_L, PAD_L + PLOT_W))
    parts = [
        chart_open(width, height, chart_id=spec.chart_id, title=spec.title, desc=spec.desc),
        _defs(),
        _axes(x_lo=x_lo, x_hi=x_hi, y_lo=y_lo, y_hi=y_hi, width=width),
    ]
    baseline = y_scale(0.0)
    for run in runs:
        if len(run) < 2:
            continue
        points = [(x_scale(point[0]), y_scale(point[1])) for point in run]
        first_x = points[0][0]
        last_x = points[-1][0]
        d = (
            path_polyline(points)
            + f" L{num(last_x)} {num(baseline)} L{num(first_x)} {num(baseline)} Z"
        )
        parts.append(
            f'<path class="pv-area" d="{d}" fill="url(#pv-grad-a-fill)" '
            'stroke="url(#pv-grad-a)" stroke-width="2" stroke-linejoin="round"/>'
        )
    parts.append(chart_close())
    return "".join(parts)


def sparkline(
    spec: ChartSpec, values: Sequence[float], *, width: int = 240, height: int = 64
) -> str:
    """A tiny axis-free trend line with a marker on the last point."""
    if len(values) < 2:
        return not_measured_panel(spec, "fewer than two points")
    lo, hi = _y_domain(values)
    x_scale = linear((0, len(values) - 1), (4, width - 4))
    y_scale = linear((lo, hi), (height - 6, 6))
    points = [(x_scale(index), y_scale(value)) for index, value in enumerate(values)]
    last_x, last_y = points[-1]
    return (
        chart_open(width, height, chart_id=spec.chart_id, title=spec.title, desc=spec.desc)
        + f'<path class="pv-spark" d="{path_polyline(points)}" fill="none" '
        'stroke="var(--pv-a1)" stroke-width="1.5" stroke-linejoin="round"/>'
        f'<circle cx="{num(last_x)}" cy="{num(last_y)}" r="2.5" fill="var(--pv-a1)"/>'
        + chart_close()
    )


def bar_chart(
    spec: ChartSpec,
    items: Sequence[BarItem],
    *,
    width: int = 720,
    height: int = 200,
    diverging: bool = False,
    group_size: int = 1,
    series_labels: Sequence[str] = (),
) -> str:
    """Vertical bars, optionally diverging or grouped by panel."""
    if width < 160:
        raise ValueError(f"chart too narrow: {width}")
    if not items:
        return not_measured_panel(spec, "no bars to draw")
    measured = [item.value for item in items if item.value is not None]
    if not measured:
        return not_measured_panel(spec, "no measured values")
    count = len(items)
    grouped = group_size > 1 and count > 1
    plot_w = max(PLOT_W, count * 10) if grouped else PLOT_W
    view_w = PAD_L + plot_w + PAD_R if grouped else width
    parts = [
        chart_open(
            view_w, height, chart_id=spec.chart_id, title=spec.title, desc=spec.desc
        )
    ]
    if grouped:
        parts.append(
            _grouped_bars(items, group_size, measured, series_labels, plot_w)
        )
    else:
        if diverging:
            lo = min(0.0, min(measured))
            hi = max(0.0, max(measured))
        else:
            lo, hi = 0.0, max(measured)
        if hi == lo:
            hi = lo + 1.0
        y_scale = linear((lo, hi), (PAD_T + 142, PAD_T))
        baseline = y_scale(0.0)
        gap = 12.0
        bar_w = min(28.0, (PLOT_W - gap * (count - 1)) / max(1, count))
        for index, item in enumerate(items):
            if item.value is None:
                continue
            x = PAD_L + index * (bar_w + gap)
            y_value = y_scale(item.value)
            top, box_height = min(y_value, baseline), abs(baseline - y_value)
            fill = "url(#pv-grad-a)"
            if diverging:
                fill = "url(#pv-grad-a)" if item.value >= 0 else "var(--pv-neg)"
            parts.append(
                f'<rect class="pv-bar" x="{num(x)}" width="{num(bar_w)}" '
                f'y="{num(top)}" height="{num(box_height)}" rx="3" fill="{fill}"/>'
            )
            if bar_w >= 16:
                parts.append(
                    f'<text x="{num(x + bar_w / 2)}" y="{num(top - 4)}" '
                    'class="pv-bar-val" text-anchor="middle">'
                    f"{esc(fmt_value(item.value, spec.decimals))}</text>"
                )
            label = item.label if len(item.label) <= 9 else item.label[:9] + "…"
            parts.append(
                f'<text x="{num(x + bar_w / 2)}" y="{height - 8}" class="pv-ax" '
                f'text-anchor="middle">{esc(label)}</text>'
            )
    parts.append(chart_close())
    return "".join(parts)


def _grouped_bars(
    items: Sequence[BarItem],
    group_size: int,
    measured: Sequence[float],
    series_labels: Sequence[str],
    plot_w: float,
) -> str:
    """Grouped bar geometry (day-major, panel-minor)."""
    n_groups = math.ceil(len(items) / group_size)
    group_w = plot_w / n_groups
    gap = 4.0
    bar_w = min(18.0, max(6.0, (group_w - gap * (group_size - 1)) / group_size))
    group_content = group_size * bar_w + gap * (group_size - 1)
    hi = max(measured) if max(measured) > 0 else 1.0
    y_scale = linear((0.0, hi), (PAD_T + 142, PAD_T))
    baseline = y_scale(0.0)
    parts: list[str] = []
    if series_labels:
        for index, label in enumerate(series_labels):
            slot = ("A", "B", "C")[index % 3]
            x = PAD_L + index * 150
            parts.append(
                f'<rect x="{x}" y="2" width="10" height="10" rx="2" '
                f'fill="{_SLOT_FILL[slot]}" stroke="var(--pv-b1)"/>'
            )
            parts.append(
                text(x + 14, 11, label, cls="pv-legend")
            )
    for group in range(n_groups):
        items_in_group = items[group * group_size:(group + 1) * group_size]
        group_x = PAD_L + group * group_w + (group_w - group_content) / 2
        for offset, item in enumerate(items_in_group):
            if item.value is None:
                continue
            slot = ("A", "B", "C")[offset % 3]
            x = group_x + offset * (bar_w + gap)
            y_value = y_scale(max(0.0, item.value))
            parts.append(
                f'<rect class="pv-bar" x="{num(x)}" width="{num(bar_w)}" '
                f'y="{num(y_value)}" height="{num(baseline - y_value)}" rx="2" '
                f'fill="{_SLOT_FILL[slot]}" stroke="var(--pv-track)"/>'
            )
        centre = PAD_L + group * group_w + group_w / 2
        label = items_in_group[0].label if items_in_group else ""
        if len(label) > 9:
            label = label[:9] + "…"
        parts.append(
            f'<text x="{num(centre)}" y="180" class="pv-ax" '
            f'text-anchor="middle">{esc(label)}</text>'
        )
    return "".join(parts)


def stacked_columns(
    spec: ChartSpec,
    items: Sequence[StackItem],
    *,
    width: int = 720,
    height: int = 200,
) -> str:
    """Measured/total columns with a track and a two-item legend."""
    if not items:
        return not_measured_panel(spec, "no columns to draw")
    parts = [
        chart_open(width, height, chart_id=spec.chart_id, title=spec.title, desc=spec.desc),
        _defs(),
    ]
    top, column_h, column_w, gap = 20.0, 140.0, 26.0, 14.0
    baseline = top + column_h
    for index, item in enumerate(items):
        x = PAD_L + index * (column_w + gap)
        parts.append(
            f'<rect class="pv-stack-track" x="{num(x)}" y="{top}" '
            f'width="{column_w}" height="{column_h}" rx="3" '
            'fill="var(--pv-track)" opacity=".55"/>'
        )
        if item.total > 0:
            fraction = max(0.0, min(1.0, item.measured / item.total))
            measured_h = column_h * fraction
            parts.append(
                f'<rect class="pv-stack-measured" x="{num(x)}" '
                f'y="{num(baseline - measured_h)}" width="{column_w}" '
                f'height="{num(measured_h)}" rx="3" fill="url(#pv-grad-b)"/>'
            )
        parts.append(
            f'<text x="{num(x + column_w / 2)}" y="{num(baseline + 16)}" '
            f'class="pv-ax" text-anchor="middle">{esc(item.label)}</text>'
        )
    legend_x = PAD_L + len(items) * (column_w + gap) + 18
    parts.append(
        f'<rect x="{num(legend_x)}" y="30" width="10" height="10" rx="2" '
        'fill="url(#pv-grad-b)"/>'
    )
    parts.append(text(legend_x + 16, 39, "measured"))
    parts.append(
        f'<rect x="{num(legend_x)}" y="48" width="10" height="10" rx="2" '
        'fill="url(#pv-hatch-b)" stroke="var(--pv-track)"/>'
    )
    parts.append(text(legend_x + 16, 57, "unknown"))
    parts.append(chart_close())
    return "".join(parts)


def strips(
    spec: ChartSpec,
    rows: Sequence[StripRow],
    *,
    width: int = 720,
    cell: tuple[int, int] = (24, 10),
) -> str:
    """Segment strips: one row of rounded cells per panel."""
    if not rows:
        return not_measured_panel(spec, "no strip rows")
    cell_w, cell_h = cell
    gap = 6
    values = [
        value for row in rows for value in row.cells if value is not None
    ]
    lo = min(values) if values else 0.0
    hi = max(values) if values else 1.0
    longest = max(len(row.cells) for row in rows)
    height = 24 + len(rows) * (cell_h + 8)
    parts = [
        chart_open(width, height, chart_id=spec.chart_id, title=spec.title, desc=spec.desc)
    ]
    for row_index, row in enumerate(rows):
        cells = list(row.cells) + [None] * (longest - len(row.cells))
        y = 18 + row_index * (cell_h + 8)
        parts.append(f'<g class="pv-strip-row" opacity="{".35" if row.off else "1"}">')
        parts.append(text(8, y + cell_h - 1, row.label))
        for column, value in enumerate(cells):
            x = 150 + column * (cell_w + gap)
            if value is None:
                parts.append(
                    f'<rect class="pv-strip-cell" x="{x}" y="{y}" width="{cell_w}" '
                    f'height="{cell_h}" rx="3" fill="none" '
                    'stroke="var(--pv-track)" stroke-dasharray="2 2"/>'
                )
                continue
            bucket = 4 if hi == lo else min(4, int((value - lo) / (hi - lo) * 5))
            parts.append(
                f'<rect class="pv-strip-cell" x="{x}" y="{y}" width="{cell_w}" '
                f'height="{cell_h}" rx="3" fill="{_RAMP[bucket]}"/>'
            )
        parts.append("</g>")
    parts.append(chart_close())
    return "".join(parts)


def calendar_heatmap(
    spec: ChartSpec,
    rows: Sequence[CalendarRow],
    *,
    width: int = 720,
    cell: int = 22,
) -> str:
    """Panel x UTC-day calendar heatmap (hollow cell = zero frames)."""
    if not rows:
        return not_measured_panel(spec, "no calendar rows")
    gap = 5
    max_days = max(len(row.cells) for row in rows)
    height = 30 + len(rows) * (cell + gap)
    parts = [
        chart_open(width, height, chart_id=spec.chart_id, title=spec.title, desc=spec.desc)
    ]
    for row_index, row in enumerate(rows):
        y = 28 + row_index * (cell + gap)
        parts.append(text(8, y + cell - 5, row.label))
        counts = [count for _date, count in row.cells]
        maximum = max(counts) if counts else 0
        previous_month = ""
        for column, (date, count) in enumerate(row.cells):
            x = 150 + column * (cell + gap)
            month = date[:7]
            if month != previous_month:
                month_name = datetime.strptime(date[:10], "%Y-%m-%d").strftime("%b")
                parts.append(
                    f'<text x="{x}" y="10" class="pv-ax">{esc(month_name)}</text>'
                )
                previous_month = month
            if count <= 0:
                parts.append(
                    f'<rect class="pv-cal-cell" x="{x}" y="{y}" width="{cell}" '
                    f'height="{cell}" rx="3" fill="none" stroke="var(--pv-track)" '
                    f'stroke-dasharray="2 2"><title>{esc(date)}: 0 frames'
                    "</title></rect>"
                )
                continue
            bucket = min(4, max(1, math.ceil(5.0 * count / maximum)) - 1)
            parts.append(
                f'<rect class="pv-cal-cell" x="{x}" y="{y}" width="{cell}" '
                f'height="{cell}" rx="3" fill="{_RAMP[bucket]}">'
                f"<title>{esc(date)}: {count} frames</title></rect>"
            )
    parts.append(chart_close())
    return "".join(parts)


def matrix_heatmap(
    spec: ChartSpec,
    rows: Sequence[tuple[str, Sequence[float | None]]],
    columns: Sequence[str],
    *,
    width: int = 720,
    cell: tuple[int, int] = (16, 14),
) -> str:
    """Coverage matrix (panel x column); values live in the drawer."""
    if not rows or not columns:
        return not_measured_panel(spec, "no matrix rows")
    cell_w, cell_h = cell
    gap = 2
    width = max(width, 180 + len(columns) * (cell_w + gap))
    height = 34 + len(rows) * (cell_h + gap)
    parts = [
        chart_open(width, height, chart_id=spec.chart_id, title=spec.title, desc=spec.desc)
    ]
    rotated = len(columns) > 8
    for column_index, column in enumerate(columns):
        x = 150 + column_index * (cell_w + gap)
        if rotated:
            parts.append(
                f'<text x="{x}" y="14" class="pv-ax" '
                f'transform="rotate(-45 {x} 14)">{esc(column)}</text>'
            )
        else:
            parts.append(
                f'<text x="{x}" y="14" class="pv-ax" font-size="9.5">'
                f"{esc(column)}</text>"
            )
    for row_index, (label, values) in enumerate(rows):
        y = 22 + row_index * (cell_h + gap)
        parts.append(text(8, y + cell_h - 3, label))
        for column_index, value in enumerate(values):
            x = 150 + column_index * (cell_w + gap)
            if value is None:
                parts.append(
                    f'<rect class="pv-matrix-cell" x="{x}" y="{y}" width="{cell_w}" '
                    f'height="{cell_h}" fill="none" stroke="var(--pv-track)" '
                    'stroke-dasharray="2 2"/>'
                )
                continue
            bucket = max(0, min(4, int(max(0.0, min(1.0, value)) * 4.999)))
            parts.append(
                f'<rect class="pv-matrix-cell" x="{x}" y="{y}" width="{cell_w}" '
                f'height="{cell_h}" fill="{_RAMP[bucket]}"/>'
            )
    parts.append(chart_close())
    return "".join(parts)


def box_plot(
    spec: ChartSpec,
    groups: Sequence[BoxGroup],
    *,
    width: int = 720,
    height: int = 220,
) -> str:
    """Min/quartile/median/max boxes, one per group."""
    if not groups:
        return not_measured_panel(spec, "no box groups")
    lo = min(group.lo for group in groups)
    hi = max(group.hi for group in groups)
    y_lo, y_hi = _y_domain([lo, hi])
    y_scale = linear((y_lo, y_hi), (PAD_T + PLOT_H, PAD_T))
    parts = [
        chart_open(width, height, chart_id=spec.chart_id, title=spec.title, desc=spec.desc),
        _defs(),
    ]
    spacing = PLOT_W / len(groups)
    for index, group in enumerate(groups):
        q1, median, q3 = group.q1, group.median, group.q3
        if q1 > median:
            q1, median = median, q1
        if q3 < median:
            q3, median = median, q3
        centre = PAD_L + (index + 0.5) * spacing
        parts.append(
            f'<line class="pv-whisker" x1="{num(centre)}" x2="{num(centre)}" '
            f'y1="{num(y_scale(group.hi))}" y2="{num(y_scale(group.lo))}" '
            'stroke="var(--pv-mut)" stroke-width="1"/>'
        )
        parts.append(
            f'<rect class="pv-box" x="{num(centre - 22)}" width="44" '
            f'y="{num(y_scale(q3))}" height="{num(abs(y_scale(q1) - y_scale(q3)))}" '
            'rx="2" fill="url(#pv-grad-b)" opacity=".7"/>'
        )
        parts.append(
            f'<line class="pv-median" x1="{num(centre - 22)}" '
            f'x2="{num(centre + 22)}" y1="{num(y_scale(median))}" '
            f'y2="{num(y_scale(median))}" stroke="var(--pv-head)" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{num(centre)}" y="{height - 8}" class="pv-ax" '
            f'text-anchor="middle">{esc(group.label)}</text>'
        )
    parts.append(chart_close())
    return "".join(parts)


def _ring_stroke(value: float) -> str:
    """Stroke colour for a measured ring value: mint, amber, or the coral gradient.

    Args:
        value: Percentage value already clamped to ``0..100``.

    Returns:
        CSS colour or gradient reference for the progress arc.
    """
    if value >= 90:
        return "var(--pv-pos)"
    if value >= 50:
        return "#E0A800"
    return "url(#pv-grad-a)"


def _ring_pct(value: float) -> str:
    """Format a ring value: whole numbers bare, fractions to one decimal."""
    rounded = round(value, 6)
    if abs(rounded - round(rounded)) < 1e-9:
        return f"{rounded:.0f}%"
    return f"{rounded:.1f}%"


def ring(
    value: float | None,
    *,
    label: str,
    chart_id: str,
    size: int = 132,
    stroke: int = 11,
) -> str:
    """One radial gauge in percent; ``None`` renders a track and an em dash."""
    radius = (size - stroke) / 2.0
    circumference = 2.0 * math.pi * radius
    centre = size / 2.0
    clamped = None if value is None else max(0.0, min(100.0, value))
    state = "not-measured" if clamped is None else "ok"
    clamped_attr = ' data-clamped="true"' if value is not None and value > 100 else ""
    parts = [
        f'<div class="pv-ring" data-state="{state}"{clamped_attr}>',
        chart_open(
            size,
            size,
            chart_id=chart_id,
            title=label,
            desc=(
                "not measured in this store"
                if clamped is None
                else f"{label}: {_ring_pct(clamped)}"
            ),
        ),
        f'<circle cx="{num(centre)}" cy="{num(centre)}" r="{num(radius)}" '
        f'fill="none" stroke="var(--pv-track)" stroke-width="{stroke}"/>',
    ]
    if clamped is not None:
        offset = circumference * (1.0 - clamped / 100.0)
        parts.append(
            f'<circle cx="{num(centre)}" cy="{num(centre)}" r="{num(radius)}" '
            f'fill="none" stroke="{_ring_stroke(clamped)}" stroke-width="{stroke}" '
            'stroke-linecap="round" '
            f'transform="rotate(-90 {num(centre)} {num(centre)})" '
            f'stroke-dasharray="{num(circumference)}" '
            f'stroke-dashoffset="{num(offset)}"/>'
        )
    parts.append(
        f'<text x="{num(centre)}" y="{num(centre + 6)}" class="pv-ring-val" '
        f'text-anchor="middle">'
        f'{"not measured" if clamped is None else _ring_pct(clamped)}</text>'
    )
    parts.append(chart_close())
    parts.append(f'<span class="pv-ring-lbl">{esc(label)}</span></div>')
    return "".join(parts)


def donut(
    segments: Sequence[DonutSegment],
    *,
    centre: str,
    chart_id: str,
    size: int = 260,
    stroke: int = 34,
) -> str:
    """Severity donut; the centre carries a label and the total count."""
    total = sum(segment.value for segment in segments)
    if not segments or total <= 0:
        return (
            '<div class="pv-empty" role="note" data-state="not-measured">'
            f'<p class="pv-empty-t">{esc(centre)}</p>'
            "<p>no numeric points in this store</p></div>"
        )
    radius = (size - stroke) / 2.0
    circumference = 2.0 * math.pi * radius
    centre_xy = size / 2.0
    colours = {"critical": "var(--pv-neg)", "warn": "var(--pv-a1)", "ok": "var(--pv-pos)"}
    heading = centre or "Findings by severity"
    parts = [
        chart_open(
            size,
            size,
            chart_id=chart_id,
            title=heading,
            desc=f"{total:g} findings by severity",
        )
    ]
    start = 0.0
    for segment in segments:
        fraction = segment.value / total if total else 0.0
        length = circumference if len(segments) == 1 else max(0.0, fraction * circumference - 2.0)
        colour = colours.get(segment.kind, "var(--pv-b1)")
        parts.append(
            f'<circle class="pv-donut-seg" data-fraction="{num(fraction, 9)}" '
            f'cx="{num(centre_xy)}" '
            f'cy="{num(centre_xy)}" r="{num(radius)}" fill="none" '
            f'stroke="{colour}" stroke-width="{stroke}" '
            f'stroke-dasharray="{num(length)} {num(circumference - length)}" '
            f'stroke-dashoffset="{num(-start)}" '
            f'transform="rotate(-90 {num(centre_xy)} {num(centre_xy)})">'
            f"<title>{esc(segment.label)}: {esc(num(segment.value, 0))} "
            f"({esc(num(fraction * 100.0, 0))}%)</title></circle>"
        )
        start += fraction * circumference
    if centre:
        parts.append(
            f'<text x="{num(centre_xy)}" y="{num(centre_xy - 2)}" class="pv-donut-lbl" '
            f'text-anchor="middle">{esc(centre)}</text>'
        )
    parts.append(
        f'<text x="{num(centre_xy)}" y="{num(centre_xy + (22 if centre else 9))}" '
        f'class="pv-donut-val" text-anchor="middle">{esc(num(total, 0))}</text>'
    )
    parts.append(chart_close())
    return "".join(parts)


def radar(
    axes: Sequence[str],
    series: Sequence[RadarSeries],
    *,
    chart_id: str,
    size: int = 320,
    rings: int = 4,
) -> str:
    """Normalised radar; every series value must already be in ``0..1``."""
    if len(axes) < 3:
        raise ValueError("radar needs at least three axes")
    if rings < 2:
        raise ValueError(f"radar needs at least two rings, got {rings}")
    for item in series:
        if len(item.values) != len(axes):
            raise ValueError("radar series length does not match axes")
        if any(value < 0.0 or value > 1.0 for value in item.values):
            raise ValueError("radar values must be normalised to 0..1")
    centre = size / 2.0
    radius = 110.0
    parts = [
        chart_open(
            size,
            size,
            chart_id=chart_id,
            title="Shape signature",
            desc="Five normalised shape axes, one polygon per panel.",
        ),
        "<defs>" + defs_hatch("pv-hatch-b", "#C159F5") + "</defs>",
    ]
    for ring_index in range(1, rings + 1):
        ring_radius = radius * ring_index / rings
        points = []
        for axis_index in range(len(axes)):
            angle = -math.pi / 2 + 2 * math.pi * axis_index / len(axes)
            points.append(
                (centre + ring_radius * math.cos(angle), centre + ring_radius * math.sin(angle))
            )
        parts.append(
            f'<polygon class="pv-radar-ring" points="'
            + " ".join(f"{num(x)},{num(y)}" for x, y in points)
            + '" fill="none" stroke="var(--pv-grid)" stroke-width="1"/>'
        )
    for axis_index, axis in enumerate(axes):
        angle = -math.pi / 2 + 2 * math.pi * axis_index / len(axes)
        x = centre + radius * math.cos(angle)
        y = centre + radius * math.sin(angle)
        parts.append(
            f'<line class="pv-axis-line" x1="{num(centre)}" y1="{num(centre)}" '
            f'x2="{num(x)}" y2="{num(y)}" stroke="var(--pv-grid)"/>'
        )
        anchor = "middle"
        if math.cos(angle) > 0.2:
            anchor = "start"
        elif math.cos(angle) < -0.2:
            anchor = "end"
        parts.append(
            f'<text x="{num(centre + (radius + 16) * math.cos(angle))}" '
            f'y="{num(centre + (radius + 16) * math.sin(angle) + 4)}" '
            f'class="pv-ax" text-anchor="{anchor}">{esc(axis)}</text>'
        )
    for item in series:
        slot = item.slot if item.slot in _SLOT_FILL else "A"
        points = []
        for axis_index, value in enumerate(item.values):
            angle = -math.pi / 2 + 2 * math.pi * axis_index / len(axes)
            points.append(
                (centre + radius * value * math.cos(angle), centre + radius * value * math.sin(angle))
            )
        dash = ' stroke-dasharray="6 4"' if slot == "B" else ""
        opacity = ".10" if slot == "B" else ".18"
        parts.append(
            f'<polygon class="pv-radar-series" data-series="{slot}" points="'
            + " ".join(f"{num(x)},{num(y)}" for x, y in points)
            + f'" fill="{_SLOT_FILL[slot]}" fill-opacity="{opacity}" '
            f'stroke="{_SLOT_STROKE[slot]}" stroke-width="2"{dash}/>'
        )
        for x, y in points:
            parts.append(
                f'<circle cx="{num(x)}" cy="{num(y)}" r="4" '
                f'fill="{_SLOT_STROKE[slot]}"/>'
            )
    parts.append(chart_close())
    return "".join(parts)
