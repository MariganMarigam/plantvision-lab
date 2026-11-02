"""Renderer tests: header validation, summaries, charts and HTML invariants."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from plantvision.analytics.dashboard import (
    Dataset,
    load_rows,
    render_charts,
    render_series_chart,
    summarize,
    write_dashboard,
)
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
