"""Renderer tests: header validation, summaries, charts and HTML invariants."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import pytest

from plantvision.analytics.dashboard import (
    Dataset,
    _alerts_section,
    _overview_card,
    _split_runs,
    load_rows,
    render_charts,
    render_series_chart,
    summarize,
    write_dashboard,
)
from plantvision.analytics.plots import PlotPoint, plot_projected_area
from plantvision.analytics.timeseries import TIMESERIES_COLUMNS

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def _dataset_rows(
    n: int = 8,
    area: float = 1000.0,
    solidity: str = "0.7",
    scale: str = "true",
) -> list[dict[str, str]]:
    """Build ``n`` hourly rows for a healthy synthetic dataset."""
    base = datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)
    rows: list[dict[str, str]] = []
    for index in range(n):
        row = {column: "" for column in TIMESERIES_COLUMNS}
        row.update(
            {
                "sha256": f"sha{index}",
                "captured_at": (
                    base + timedelta(hours=index)
                ).isoformat().replace("+00:00", "Z"),
                "camera_id": "cam",
                "zone_id": "z",
                "area_px": str(area + index),
                "area_cm2": "12.5",
                "roi_fraction_pct": "20.0",
                "solidity": solidity,
                "extent": "0.5",
                "scale_ok": scale,
                "quality_flag": "",
                "settings_source": "exif",
            }
        )
        rows.append(row)
    return rows


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write rows with the canonical header."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TIMESERIES_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_load_rows_rejects_foreign_header(tmp_path: Path) -> None:
    path = tmp_path / "foreign.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        load_rows(path)
    message = str(excinfo.value)
    assert "a" in message
    assert "sha256" in message


def test_load_rows_accepts_prefix_header(tmp_path: Path) -> None:
    path = tmp_path / "prefix.csv"
    columns = TIMESERIES_COLUMNS[:15]
    row = _dataset_rows(1)[0]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerow(row)
    rows = load_rows(path)
    assert len(rows) == 1
    assert rows[0]["sha256"] == "sha0"


def test_load_rows_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_rows(tmp_path / "missing.csv")


def test_summarize_counts_scale_quality_and_duplicates() -> None:
    rows = _dataset_rows(8)
    rows[0]["quality_flag"] = "blur"
    rows[1]["quality_flag"] = "dark"
    rows[7]["sha256"] = rows[0]["sha256"]
    summary = summarize("x", "src", rows, now=NOW)
    assert summary.rows == 8
    assert summary.zones == 1
    assert summary.scale_pct == pytest.approx(100.0)
    assert summary.quality_rate_pct == pytest.approx(25.0)
    assert summary.solidity_rows == 8
    assert summary.area_cm2_rows == 8
    assert summary.duplicates == 1


def test_render_series_chart_writes_png(tmp_path: Path) -> None:
    png = tmp_path / "area.png"
    render_series_chart(
        _dataset_rows(8), "area_px", title="t", ylabel="area (px)",
        color="#4caf50", out_png=png,
    )
    assert png.is_file()
    assert png.stat().st_size > 1000


def test_render_series_chart_empty_raises(tmp_path: Path) -> None:
    rows = _dataset_rows(3)
    for row in rows:
        row["area_px"] = ""
    with pytest.raises(ValueError):
        render_series_chart(
            rows, "area_px", title="t", ylabel="area (px)",
            color="#4caf50", out_png=tmp_path / "empty.png",
        )


def test_render_charts_skips_absent_metrics(tmp_path: Path) -> None:
    rows = _dataset_rows(8, solidity="")
    for row in rows:
        row["extent"] = ""
    charts = render_charts(rows, tmp_path, label="x", pipeline_version="v")
    titles = [chart.title for chart in charts]
    assert any("projected area (px)" in title for title in titles)
    assert not any("shape" in title for title in titles)


def test_write_dashboard_creates_self_contained_html(tmp_path: Path) -> None:
    source = tmp_path / "data.csv"
    _write_csv(source, _dataset_rows(8))
    out = tmp_path / "out" / "index.html"
    result = write_dashboard([Dataset("x", source)], out, now=NOW)
    document = out.read_text(encoding="utf-8")
    assert "data:image/png;base64," in document
    assert 'src="http' not in document
    assert '<section id="alerts">' in document
    assert result.datasets == 1
    assert result.rows_total == 8


def test_html_escapes_dataset_label(tmp_path: Path) -> None:
    source = tmp_path / "data.csv"
    _write_csv(source, _dataset_rows(4))
    out = tmp_path / "index.html"
    write_dashboard([Dataset("<b>x</b>", source)], out, now=NOW)
    document = out.read_text(encoding="utf-8")
    assert "&lt;b&gt;x&lt;/b&gt;" in document
    assert "<b>x</b>" not in document


def test_html_has_alt_text_for_every_chart(tmp_path: Path) -> None:
    source = tmp_path / "data.csv"
    _write_csv(source, _dataset_rows(8))
    out = tmp_path / "index.html"
    write_dashboard([Dataset("x", source)], out, now=NOW)
    document = out.read_text(encoding="utf-8")
    assert document.count("<img") == document.count("alt=")


def test_empty_dataset_renders_note(tmp_path: Path) -> None:
    source = tmp_path / "empty.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=TIMESERIES_COLUMNS).writeheader()
    out = tmp_path / "index.html"
    write_dashboard([Dataset("empty", source)], out, now=NOW)
    document = out.read_text(encoding="utf-8")
    assert "No rule triggered" in document
    assert "No chartable metrics" in document


def test_duplicate_dataset_labels_raise(tmp_path: Path) -> None:
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    _write_csv(first, _dataset_rows(4))
    _write_csv(second, _dataset_rows(4))
    with pytest.raises(ValueError):
        write_dashboard(
            [Dataset("x", first), Dataset("x", second)],
            tmp_path / "index.html",
            now=NOW,
        )


def test_dataset_note_rendered_in_section(tmp_path: Path) -> None:
    """A dataset note appears under Source and the label gets its slug anchor."""
    source = tmp_path / "data.csv"
    _write_csv(source, _dataset_rows(4))
    out = tmp_path / "index.html"
    write_dashboard(
        [Dataset("basil farm-02 · SAM2", source, "SAM2 mask series")],
        out,
        now=NOW,
    )
    document = out.read_text(encoding="utf-8")
    assert "basil farm-02 · SAM2" in document
    assert "SAM2 mask series" in document
    assert 'id="dataset-basil-farm-02-sam2"' in document
    assert '<p class="muted">SAM2 mask series</p>' in document


def test_dataset_note_absent_when_empty(tmp_path: Path) -> None:
    """No note means no empty muted paragraph; Source is still rendered."""
    source = tmp_path / "data.csv"
    _write_csv(source, _dataset_rows(4))
    out = tmp_path / "index.html"
    write_dashboard([Dataset("x", source)], out, now=NOW)
    document = out.read_text(encoding="utf-8")
    assert "Source:" in document
    assert 'class="muted"></p>' not in document


def test_series_runs_split_on_capture_gap() -> None:
    """A hole larger than 3x the median gap becomes a separate run."""
    base = datetime(2026, 10, 30, 0, 0, tzinfo=timezone.utc)
    points = [
        (base + timedelta(hours=offset), float(offset))
        for offset in (0, 1, 2, 18, 19)
    ]
    runs = _split_runs(points)
    assert [len(run) for run in runs] == [3, 2]
    assert runs[1][0][0] == base + timedelta(hours=18)


def test_plots_split_runs_on_capture_gap() -> None:
    """The cm2 renderer uses the same gap rule."""
    from plantvision.analytics.plots import _split_runs as plot_runs

    base = datetime(2026, 10, 30, 0, 0, tzinfo=timezone.utc)
    points = [
        (base + timedelta(hours=offset),
         PlotPoint((base + timedelta(hours=offset)).isoformat(), 10.0, ()))
        for offset in (0, 1, 2, 18, 19)
    ]
    assert [len(run) for run in plot_runs(points)] == [3, 2]


def test_card_says_not_measured_when_quality_flag_is_blank() -> None:
    """Zero non-blank quality_flag cells must not read as 0.0% clean."""
    rows = _dataset_rows(8)
    for row in rows:
        row["quality_flag"] = ""
    card = _overview_card(summarize("x", "src", rows, now=NOW))
    assert "not measured" in card
    assert "Quality-flag rate</dt><dd>0.0%" not in card


def test_card_has_verdict_age_and_area_delta() -> None:
    """The card answers the crop: verdict + age, then first->last area."""
    rows = _dataset_rows(8)
    card = _overview_card(summarize("x", "src", rows, now=NOW))
    assert "WARN" in card
    assert "1.2 days" in card
    assert "+0.7%" in card
    assert "Zones" not in card
    assert "Duplicates" not in card
    assert "Scale coverage (all frames)" in card


def test_plot_facecolor_and_ink_change_output(tmp_path: Path) -> None:
    """Omitted kwargs stay light; explicit kwargs paint the dark page."""
    points = [
        PlotPoint("2026-10-31T00:00:00Z", 10.0, ()),
        PlotPoint("2026-10-31T01:00:00Z", 12.0, ()),
    ]
    light = tmp_path / "light.png"
    dark = tmp_path / "dark.png"
    plot_projected_area(points, "z", "v", light)
    plot_projected_area(
        points, "z", "v", dark, facecolor="#171b18", ink="#a8b3ab"
    )
    light_px = cv2.imread(str(light))[0, 0]
    dark_px = cv2.imread(str(dark))[0, 0]
    assert all(channel > 200 for channel in light_px)
    assert all(channel < 60 for channel in dark_px)


def test_chart_png_uses_dashboard_size_and_no_em_dash_titles(tmp_path: Path) -> None:
    """Charts are 9x3.2 in at 180 dpi and titles use the middle dot."""
    png = tmp_path / "chart.png"
    render_series_chart(
        _dataset_rows(8), "area_px", title="t", ylabel="area (px)",
        color="#4caf50", out_png=png,
    )
    assert cv2.imread(str(png)).shape[:2] == (576, 1620)
    charts = render_charts(_dataset_rows(8), tmp_path, label="x", pipeline_version="v")
    assert all("—" not in chart.title for chart in charts)
    assert all(" · " in chart.title for chart in charts)


def test_alert_table_has_fixed_widths_and_short_window(tmp_path: Path) -> None:
    """The alert table is dense: colgroup + formatted window."""
    rows = _dataset_rows(8)
    rows[7]["captured_at"] = (datetime(
        2026, 10, 31, 20, 0, tzinfo=timezone.utc
    )).isoformat().replace("+00:00", "Z")
    html_text = _alerts_section([summarize("x", "src", rows, now=NOW)])
    assert 'class="alert-table"' in html_text
    assert "<colgroup>" in html_text
    assert 'style="width:8%"' in html_text
    assert "31 Oct 06:00 -> 31 Oct 20:00" in html_text


def test_alerts_link_to_existing_dataset_and_chart_ids(tmp_path: Path) -> None:
    """Alert rows link to the dataset section and the relevant chart figure."""
    source = tmp_path / "data.csv"
    rows = _dataset_rows(10)
    for row in rows[5:]:
        row["scale_ok"] = "false"
    rows[9]["captured_at"] = (datetime(
        2026, 11, 1, 1, 0, tzinfo=timezone.utc
    )).isoformat().replace("+00:00", "Z")
    _write_csv(source, rows)
    out = tmp_path / "index.html"
    write_dashboard([Dataset("x", source)], out, now=NOW)
    document = out.read_text(encoding="utf-8")
    assert 'id="chart-x-px"' in document
    assert 'id="chart-x-cm2"' in document
    assert '<a href="#dataset-x">x / z</a>' in document
    assert 'href="#chart-x-cm2">scale-coverage</a>' in document
    assert 'href="#chart-x-px">capture-gap</a>' in document


def test_coverage_table_sits_below_charts(tmp_path: Path) -> None:
    """The dense per-column table follows its charts."""
    source = tmp_path / "data.csv"
    _write_csv(source, _dataset_rows(8))
    out = tmp_path / "index.html"
    write_dashboard([Dataset("x", source)], out, now=NOW)
    document = out.read_text(encoding="utf-8")
    assert '<table class="coverage">' in document
    assert document.index('<div class="charts">') < document.index(
        '<table class="coverage">'
    )


def test_default_html_title_has_no_em_dash(tmp_path: Path) -> None:
    """The page title uses the middle dot, not an em dash."""
    source = tmp_path / "data.csv"
    _write_csv(source, _dataset_rows(4))
    out = tmp_path / "index.html"
    write_dashboard([Dataset("x", source)], out, now=NOW)
    document = out.read_text(encoding="utf-8")
    title = document.split("<title>", 1)[1].split("</title>", 1)[0]
    assert "—" not in title
    assert " · " in title
