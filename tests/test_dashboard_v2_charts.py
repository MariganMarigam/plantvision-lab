"""Geometry and accessibility tests for the v2 SVG chart primitives."""

from __future__ import annotations

import math
import re

from plantvision.analytics.dashboard.charts import (
    Band,
    BarItem,
    BoxGroup,
    CalendarRow,
    ChartSpec,
    DonutSegment,
    PlotSeries,
    RadarSeries,
    StackItem,
    StripRow,
    area_chart,
    bar_chart,
    box_plot,
    calendar_heatmap,
    donut,
    line_chart,
    matrix_heatmap,
    not_measured_panel,
    radar,
    ring,
    sparkline,
    stacked_columns,
    strips,
)

SPEC = ChartSpec(chart_id="ch-test", title="Test chart", desc="What and now.")


def _attrs(markup: str, tag: str) -> list[dict[str, str]]:
    """Return attributes of every ``<tag ...>`` occurrence."""
    found: list[dict[str, str]] = []
    for match in re.finditer(rf"<{tag}\b([^>]*)>", markup):
        attrs = dict(re.findall(r'([a-zA-Z-]+)="([^"]*)"', match.group(1)))
        found.append(attrs)
    return found


def test_line_has_one_path_per_run() -> None:
    markup = line_chart(
        SPEC,
        [PlotSeries("A", [[(0, 1.0), (1000, 2.0)], [(20000, 3.0), (21000, 4.0)]])],
    )
    assert markup.count('class="pv-line') == 2
    assert markup.count("<g data-series=") == 1


def test_line_breaks_on_capture_gap() -> None:
    markup = line_chart(
        SPEC,
        [PlotSeries("A", [[(0, 1.0), (1000, 2.0)], [(100000, 3.0), (101000, 4.0)]])],
    )
    paths = re.findall(r'class="pv-line[^"]*" d="([^"]*)"', markup)
    assert len(paths) == 2
    # Each path is a single connected run: no "L" command can jump the gap.
    assert paths[0].count("L") == 1
    assert paths[1].count("L") == 1


def test_line_draws_threshold_band() -> None:
    markup = line_chart(
        SPEC,
        [PlotSeries("A", [[(0, 0.0), (1000, 1.0)]])],
        bands=(Band(lo=0.4, hi=0.6, kind="warn"),),
    )
    rects = [
        attrs for attrs in _attrs(markup, "rect")
        if attrs.get("fill") == "url(#pv-band-warn)"
    ]
    assert len(rects) == 1
    assert float(rects[0]["height"]) > 0.0
    assert float(rects[0]["width"]) == 650.0


def test_line_marks_missing_scale_points() -> None:
    markup = line_chart(
        SPEC,
        [PlotSeries("A", [[(0, 1.0), (3000, 2.0)]])],
        missing=(0, 1000, 2000, 3000),
    )
    assert markup.count('class="pv-miss"') == 4


def test_bar_width_and_gap_geometry() -> None:
    items = [BarItem(f"d{index}", float(index + 1)) for index in range(9)]
    markup = bar_chart(SPEC, items)
    bars = [a for a in _attrs(markup, "rect") if a.get("class") == "pv-bar"]
    assert len(bars) == 9
    widths = [float(attrs["width"]) for attrs in bars]
    xs = [float(attrs["x"]) for attrs in bars]
    assert abs(widths[0] - 28.0) < 0.01
    assert abs(xs[1] - xs[0] - 40.0) < 0.01
    assert abs(xs[0] - 52.0) < 0.01


def test_stacked_columns_measured_fraction() -> None:
    markup = stacked_columns(SPEC, [StackItem("basil", measured=516, total=843)])
    measured = [
        a for a in _attrs(markup, "rect") if a.get("class") == "pv-stack-measured"
    ]
    assert len(measured) == 1
    assert abs(float(measured[0]["height"]) - 140.0 * 516 / 843) < 0.5


def test_ring_dashoffset_matches_value() -> None:
    markup = ring(72, label="scale", chart_id="ch-ring")
    circles = [a for a in _attrs(markup, "circle") if "stroke-dashoffset" in a]
    assert len(circles) == 1
    circumference = 2 * math.pi * (132 - 11) / 2
    assert abs(float(circles[0]["stroke-dashoffset"]) - circumference * 0.28) < 0.01
    assert "72%" in markup


def test_ring_not_measured_when_none() -> None:
    markup = ring(None, label="quality", chart_id="ch-ring-none")
    assert "—" in markup
    assert 'data-state="not-measured"' in markup
    assert "0%" not in markup


def test_donut_segments_sum_to_360() -> None:
    markup = donut(
        [DonutSegment("critical", 3), DonutSegment("warn", 6), DonutSegment("ok", 0)],
        centre="findings",
        chart_id="ch-donut",
    )
    segments = [
        a for a in _attrs(markup, "circle") if a.get("class") == "pv-donut-seg"
    ]
    assert len(segments) == 3
    fractions = [float(attrs["data-fraction"]) for attrs in segments]
    assert abs(sum(fractions) - 1.0) < 1e-6


def test_radar_has_five_axes_and_two_polygons() -> None:
    markup = radar(
        ["solidity", "extent", "hull", "perimeter", "ellipse"],
        [
            RadarSeries("A", [0.1, 0.2, 0.3, 0.4, 0.5], slot="A"),
            RadarSeries("B", [0.5, 0.4, 0.3, 0.2, 0.1], slot="B"),
        ],
        chart_id="ch-radar",
    )
    assert len([a for a in _attrs(markup, "line") if a.get("class") == "pv-axis-line"]) == 5
    polygons = [a for a in _attrs(markup, "polygon") if a.get("class") == "pv-radar-series"]
    assert len(polygons) == 2
    assert "url(#pv-hatch-b)" in polygons[1].get("fill", "")


def test_calendar_cell_count_matches_days() -> None:
    days = [("2026-10-16", 1), ("2026-10-17", 2)]
    rows = [CalendarRow(f"panel{index}", days) for index in range(3)]
    markup = calendar_heatmap(SPEC, rows)
    assert markup.count('class="pv-cal-cell"') == 6
    rows_17 = [CalendarRow(f"panel{index}", [(f"2026-10-{day:02d}", 1) for day in range(1, 18)]) for index in range(3)]
    assert calendar_heatmap(SPEC, rows_17).count('class="pv-cal-cell"') == 51


def test_chart_svg_has_title_and_desc() -> None:
    outputs = [
        line_chart(SPEC, [PlotSeries("A", [[(0, 1.0), (1000, 2.0)]])]),
        area_chart(SPEC, [[(0, 1.0), (1000, 2.0)]]),
        sparkline(SPEC, [1.0, 2.0, 3.0]),
        bar_chart(SPEC, [BarItem("a", 1.0)]),
        stacked_columns(SPEC, [StackItem("a", 1.0, 2.0)]),
        strips(SPEC, [StripRow("a", [1.0, None])]),
        calendar_heatmap(SPEC, [CalendarRow("a", [("2026-10-16", 2)])]),
        matrix_heatmap(SPEC, [("a", [0.5, None])], ["x", "y"]),
        box_plot(SPEC, [BoxGroup("a", 1.0, 2.0, 3.0, 4.0, 5.0)]),
        ring(50, label="scale", chart_id="ch-r"),
        donut([DonutSegment("a", 1.0)], centre="total", chart_id="ch-d"),
        radar(
            ["a", "b", "c"],
            [RadarSeries("A", [0.1, 0.2, 0.3])],
            chart_id="ch-rad",
        ),
    ]
    for markup in outputs:
        assert re.search(r"<title id=\"[^\"]+-t\">", markup)
        assert "<desc>" in markup
    assert 'class="pv-empty"' in not_measured_panel(SPEC, "no numeric points")
