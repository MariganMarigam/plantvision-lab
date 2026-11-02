"""Static, self-contained growth dashboard built from metrics CSVs.

Reads validated time-series stores, evaluates the deterministic rules and
renders one HTML document whose CSS and PNG charts are embedded. No server,
no JavaScript, no new dependency.
"""

from __future__ import annotations

import base64
import csv
import html
import math
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from plantvision.analytics.plots import plot_projected_area
from plantvision.analytics.rules import (
    Finding,
    RuleConfig,
    evaluate_rules,
    is_true,
    parse_timestamp,
    quality_flags,
)
from plantvision.analytics.timeseries import (
    TIMESERIES_COLUMNS,
    points_from_rows,
    read_timeseries,
)

_DAY_SECONDS = 86400.0


@dataclass(frozen=True)
class Dataset:
    """A named CSV store to render."""

    label: str
    csv_path: Path


@dataclass(frozen=True)
class Chart:
    """One rendered chart: title, alt text and the PNG on disk."""

    title: str
    alt: str
    png_path: Path


@dataclass(frozen=True)
class DatasetSummary:
    """Deterministic per-dataset statistics and rule findings."""

    label: str
    source: str
    rows: int
    zones: int
    first_at: str
    last_at: str
    span_hours: float | None
    last_age_days: float | None
    scale_pct: float
    quality_rate_pct: float
    solidity_rows: int
    area_cm2_rows: int
    duplicates: int
    coverage: tuple[tuple[str, int], ...]
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class DashboardResult:
    """What one :func:`write_dashboard` call produced."""

    out_path: Path
    datasets: int
    rows_total: int
    findings: tuple[Finding, ...]
    charts: int


_COVERAGE_COLUMNS: tuple[str, ...] = (
    "area_px", "area_cm2", "roi_fraction_pct", "solidity", "extent",
    "px_per_mm", "scale_ok", "quality_flag", "settings_source",
)


def _escape(value: object) -> str:
    """HTML-escape any dynamic value (quotes included)."""
    return html.escape(str(value), quote=True)


def _slug(label: str) -> str:
    """Anchor-safe slug for a dataset label."""
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "dataset"


def _cell(row: dict[str, str], key: str) -> str:
    """Trimmed cell value (empty string when absent)."""
    return (row.get(key) or "").strip()


def _finite(row: dict[str, str], key: str) -> float | None:
    """Read a finite float from a row cell; blank/invalid -> ``None``."""
    raw = _cell(row, key)
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def _has_numeric(rows: Sequence[dict[str, str]], key: str) -> bool:
    """Whether any row carries a finite numeric value in ``key``."""
    return any(_finite(row, key) is not None for row in rows)


def load_rows(path: Path) -> list[dict[str, str]]:
    """Read a metrics CSV after validating its header.

    Args:
        path: CSV path.

    Returns:
        One dict per data row.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the header is neither the canonical schema nor a strict
            prefix of it.
    """
    if not path.is_file():
        raise FileNotFoundError(f"dataset not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            header = tuple(next(reader))
        except StopIteration:
            header = ()
    if header != TIMESERIES_COLUMNS and header != TIMESERIES_COLUMNS[: len(header)]:
        raise ValueError(
            f"timeseries header mismatch: file={header} "
            f"expected={TIMESERIES_COLUMNS}"
        )
    return read_timeseries(path)


def summarize(
    label: str,
    source: str,
    rows: Sequence[dict[str, str]],
    *,
    now: datetime,
    config: RuleConfig | None = None,
) -> DatasetSummary:
    """Compute per-dataset statistics and evaluate the rules.

    Args:
        label: Display label.
        source: Human-readable source path.
        rows: Parsed CSV rows.
        now: Reference time for age rules (naive treated as UTC).
        config: Optional rule thresholds.

    Returns:
        The filled :class:`DatasetSummary`.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    dated = [
        (timestamp, row)
        for row in rows
        if (timestamp := parse_timestamp(row.get("captured_at"))) is not None
    ]
    dated.sort(key=lambda pair: pair[0])

    first_at = dated[0][0].isoformat() if dated else ""
    last_at = dated[-1][0].isoformat() if dated else ""
    span_hours: float | None = None
    last_age_days: float | None = None
    if dated:
        span_hours = (dated[-1][0] - dated[0][0]).total_seconds() / 3600.0
        last_age_days = max(0.0, (now - dated[-1][0]).total_seconds() / _DAY_SECONDS)

    total = len(rows)
    scale_pct = (
        100.0 * sum(1 for row in rows if is_true(row.get("scale_ok"))) / total
        if total else 0.0
    )
    quality_rate_pct = (
        100.0 * sum(1 for row in rows if quality_flags(row.get("quality_flag"))) / total
        if total else 0.0
    )
    solidity_rows = sum(1 for row in rows if _cell(row, "solidity"))
    area_cm2_rows = sum(1 for row in rows if _cell(row, "area_cm2"))
    sha_values = {_cell(row, "sha256") for row in rows if _cell(row, "sha256")}
    duplicates = total - len(sha_values)
    zones = len({_cell(row, "zone_id") or "unknown" for row in rows})
    coverage = tuple(
        (column, sum(1 for row in rows if _cell(row, column)))
        for column in _COVERAGE_COLUMNS
    )
    findings = tuple(evaluate_rules(rows, now=now, config=config))

    return DatasetSummary(
        label=label,
        source=source,
        rows=total,
        zones=zones,
        first_at=first_at,
        last_at=last_at,
        span_hours=span_hours,
        last_age_days=last_age_days,
        scale_pct=scale_pct,
        quality_rate_pct=quality_rate_pct,
        solidity_rows=solidity_rows,
        area_cm2_rows=area_cm2_rows,
        duplicates=duplicates,
        coverage=coverage,
        findings=findings,
    )


def _style_axes(ax: object, *, title: str, ylabel: str, fig: object) -> None:
    """Apply the shared dark theme to one matplotlib axis."""
    fig.patch.set_facecolor("#171b18")  # type: ignore[attr-defined]
    ax.set_facecolor("#171b18")  # type: ignore[attr-defined]
    ax.grid(True, color="#2a332c")  # type: ignore[attr-defined]
    for spine in ax.spines.values():  # type: ignore[attr-defined]
        spine.set_color("#2a332c")
    ax.tick_params(colors="#a8b3ab")  # type: ignore[attr-defined]
    ax.xaxis.label.set_color("#a8b3ab")  # type: ignore[attr-defined]
    ax.yaxis.label.set_color("#a8b3ab")  # type: ignore[attr-defined]
    ax.title.set_color("#e8ede9")  # type: ignore[attr-defined]
    ax.set_xlabel("captured_at (UTC)")  # type: ignore[attr-defined]
    ax.set_ylabel(ylabel)  # type: ignore[attr-defined]
    ax.set_title(title, loc="left")  # type: ignore[attr-defined]


def render_series_chart(
    rows: Sequence[dict[str, str]],
    metric: str,
    *,
    title: str,
    ylabel: str,
    color: str,
    out_png: Path,
) -> None:
    """Render one metric over time as a dark-theme PNG.

    Args:
        rows: Parsed CSV rows.
        metric: Numeric column to plot.
        title: Chart title.
        ylabel: Y-axis label.
        color: Series colour.
        out_png: Destination PNG path.

    Raises:
        ValueError: If no numeric ``metric`` values exist.
    """
    points: list[tuple[datetime, float]] = []
    for row in rows:
        timestamp = parse_timestamp(row.get("captured_at"))
        if timestamp is None:
            continue
        value = _finite(row, metric)
        if value is None:
            continue
        points.append((timestamp, value))
    points.sort(key=lambda pair: pair[0])
    if not points:
        raise ValueError(f"no {metric} data")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4))
    _style_axes(ax, title=title, ylabel=ylabel, fig=fig)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    ax.plot(xs, ys, color=color, linewidth=1.4)
    ax.scatter(xs, ys, s=12, color=color)
    fig.autofmt_xdate()
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)


def render_shape_chart(
    rows: Sequence[dict[str, str]], *, title: str, out_png: Path
) -> None:
    """Render solidity and extent series on one dark-theme axis.

    Args:
        rows: Parsed CSV rows.
        title: Chart title.
        out_png: Destination PNG path.

    Raises:
        ValueError: If neither solidity nor extent has numeric data.
    """
    series: dict[str, list[tuple[datetime, float]]] = {"solidity": [], "extent": []}
    for metric in series:
        for row in rows:
            timestamp = parse_timestamp(row.get("captured_at"))
            if timestamp is None:
                continue
            value = _finite(row, metric)
            if value is None:
                continue
            series[metric].append((timestamp, value))
        series[metric].sort(key=lambda pair: pair[0])
    if not series["solidity"] and not series["extent"]:
        raise ValueError("no shape-trait data")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4))
    _style_axes(ax, title=title, ylabel="ratio (0–1)", fig=fig)
    colors = {"solidity": "#e0a800", "extent": "#ab47bc"}
    for metric, points in series.items():
        if not points:
            continue
        ax.plot(
            [point[0] for point in points],
            [point[1] for point in points],
            color=colors[metric], linewidth=1.4, label=metric,
        )
        ax.scatter(
            [point[0] for point in points],
            [point[1] for point in points],
            s=12, color=colors[metric],
        )
    legend = ax.legend()
    for text in legend.get_texts():
        text.set_color("#e8ede9")
    fig.autofmt_xdate()
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)


def render_charts(
    rows: Sequence[dict[str, str]],
    out_dir: Path,
    *,
    label: str,
    pipeline_version: str,
) -> list[Chart]:
    """Render every chart the dataset supports and return their metadata.

    Args:
        rows: Parsed CSV rows.
        out_dir: Directory for the temporary PNGs.
        label: Dataset label used in titles/alt text.
        pipeline_version: Passed through to the cm² plot title.

    Returns:
        The rendered charts (possibly empty).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    charts: list[Chart] = []

    if _has_numeric(rows, "area_px"):
        png = out_dir / "area-px.png"
        title = f"{label} — projected area (px)"
        render_series_chart(
            rows, "area_px", title=title, ylabel="area (px)",
            color="#4caf50", out_png=png,
        )
        charts.append(Chart(
            title=title,
            alt=f"{label}: projected plant area in pixels over capture time",
            png_path=png,
        ))

    if any(_cell(row, "area_cm2") for row in rows):
        png = out_dir / "area-cm2.png"
        zones = {_cell(row, "zone_id") for row in rows if _cell(row, "zone_id")}
        zone_label = ", ".join(sorted(zones)) or label
        plot_projected_area(
            points_from_rows(rows), zone_label, pipeline_version, png
        )
        charts.append(Chart(
            title=f"{label} — projected area (cm²)",
            alt=(
                "projected area in cm²; red × marks frames without a detected "
                "scale marker"
            ),
            png_path=png,
        ))

    if _has_numeric(rows, "roi_fraction_pct"):
        png = out_dir / "roi.png"
        title = f"{label} — plant share of ROI (%)"
        render_series_chart(
            rows, "roi_fraction_pct", title=title,
            ylabel="plant share of ROI (%)", color="#5b9bd5", out_png=png,
        )
        charts.append(Chart(
            title=title,
            alt=f"{label}: plant share of the region of interest over capture time",
            png_path=png,
        ))

    if _has_numeric(rows, "solidity") or _has_numeric(rows, "extent"):
        png = out_dir / "shape.png"
        title = f"{label} — shape traits (solidity, extent)"
        render_shape_chart(rows, title=title, out_png=png)
        charts.append(Chart(
            title=title,
            alt=f"{label}: solidity and extent shape ratios over capture time",
            png_path=png,
        ))

    return charts


_CSS = """
:root {
  --bg: #0f1210;
  --surface: #171b18;
  --surface-2: #1f2521;
  --border: #2a332c;
  --text: #e8ede9;
  --muted: #a8b3ab;
  --accent: #4caf50;
  --critical-bg: #5c1a17;
  --critical-fg: #ffb4ab;
  --warn-bg: #4a3a00;
  --warn-fg: #ffd479;
  --ok-bg: #12351f;
  --ok-fg: #9ae6b4;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 16px;
  --space-4: 24px;
  --space-5: 32px;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
}
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
.wrap { max-width: 1200px; margin: 0 auto; padding: var(--space-4); }
a { color: var(--accent); }
a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.skip {
  position: absolute; left: -999px; top: 0;
  background: var(--surface-2); color: var(--text);
  padding: var(--space-2) var(--space-3);
}
.skip:focus { left: var(--space-2); }
header h1 { margin: 0 0 var(--space-2); }
.muted { color: var(--muted); }
nav ul { list-style: none; display: flex; flex-wrap: wrap; gap: var(--space-3); padding: 0; }
nav a { text-decoration: none; }
nav a:hover, nav a:focus-visible { text-decoration: underline; }
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--space-3);
}
.card, .chart {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: var(--space-3);
}
.card h3 { margin: 0 0 var(--space-2); }
.card dl { display: grid; grid-template-columns: auto 1fr; gap: var(--space-1) var(--space-3); margin: 0; }
.card dt { color: var(--muted); }
.card dd { margin: 0; font-variant-numeric: tabular-nums; }
.charts { display: grid; grid-template-columns: 1fr; gap: var(--space-3); }
.chart { padding: var(--space-2); }
.chart img { width: 100%; height: auto; display: block; }
.chart figcaption { color: var(--muted); padding: var(--space-1) var(--space-2) 0; }
.badge {
  display: inline-block;
  border-radius: 999px;
  padding: 2px var(--space-2);
  font-size: 0.8rem;
  font-weight: 600;
}
.badge-critical { background: var(--critical-bg); color: var(--critical-fg); }
.badge-warn { background: var(--warn-bg); color: var(--warn-fg); }
.badge-ok { background: var(--ok-bg); color: var(--ok-fg); }
table {
  width: 100%;
  border-collapse: collapse;
  font-variant-numeric: tabular-nums;
}
caption { text-align: left; color: var(--muted); padding-bottom: var(--space-2); }
td, th { padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
th[scope=col] { color: var(--muted); text-transform: uppercase; font-size: 0.85rem; letter-spacing: 0.04em; }
.empty { color: var(--muted); background: var(--surface-2); border-radius: 8px; padding: var(--space-3); }
footer { color: var(--muted); }
"""


def _badge(severity: str) -> str:
    """Render a severity badge."""
    css = {"critical": "badge-critical", "warn": "badge-warn"}.get(
        severity, "badge-ok"
    )
    return f'<span class="badge {css}">{_escape(severity.upper())}</span>'


def _age_badge(age_days: float | None) -> str:
    """Render last-frame age with its severity badge."""
    if age_days is None:
        return '<span class="muted">n/a</span>'
    if age_days >= 7.0:
        badge = "badge-critical"
    elif age_days >= 2.0:
        badge = "badge-warn"
    else:
        badge = "badge-ok"
    return f'<span class="badge {badge}">{age_days:.1f} days</span>'


def _fmt_number(value: float | None) -> str:
    """Format an optional number for the findings table."""
    return "" if value is None else f"{value:.2f}"


def _overview_card(summary: DatasetSummary) -> str:
    """Render one dataset overview card."""
    span = f"{summary.span_hours:.1f} h" if summary.span_hours is not None else "n/a"
    date_range = (
        f"{_escape(summary.first_at)} → {_escape(summary.last_at)}"
        if summary.first_at else "n/a"
    )
    return (
        '<article class="card">'
        f"<h3>{_escape(summary.label)}</h3>"
        "<dl>"
        f"<dt>Frames</dt><dd>{summary.rows}</dd>"
        f"<dt>Zones</dt><dd>{summary.zones}</dd>"
        f"<dt>Date range</dt><dd>{date_range}</dd>"
        f"<dt>Span</dt><dd>{_escape(span)}</dd>"
        f"<dt>Last frame</dt><dd>{_age_badge(summary.last_age_days)}</dd>"
        f"<dt>Scale coverage</dt><dd>{summary.scale_pct:.1f}%</dd>"
        f"<dt>Quality-flag rate</dt><dd>{summary.quality_rate_pct:.1f}%</dd>"
        f"<dt>Solidity rows</dt><dd>{summary.solidity_rows}/{summary.rows}</dd>"
        f"<dt>Duplicates</dt><dd>{summary.duplicates}</dd>"
        "</dl>"
        "</article>"
    )


def _alerts_section(
    summaries: Sequence[DatasetSummary],
) -> str:
    """Render the deterministic findings table (or the empty-state note)."""
    tagged = [
        (summary.label, finding)
        for summary in summaries
        for finding in summary.findings
    ]
    tagged.sort(key=lambda pair: (
        {"critical": 0, "warn": 1}.get(pair[1].severity, 2),
        pair[0], pair[1].zone, pair[1].rule_id,
    ))
    if not tagged:
        return (
            '<section id="alerts">'
            "<h2>Alerts</h2>"
            '<p class="empty">No rule triggered — every metric is inside its '
            "threshold.</p>"
            "</section>"
        )
    rows = []
    for label, finding in tagged:
        window = ""
        if finding.window_start or finding.window_end:
            window = f"{_escape(finding.window_start)} → {_escape(finding.window_end)}"
        rows.append(
            "<tr>"
            f"<td>{_badge(finding.severity)}</td>"
            f"<td>{_escape(label)} / {_escape(finding.zone)}</td>"
            f"<td>{_escape(finding.rule_id)}</td>"
            f"<td>{_escape(finding.detail)}</td>"
            f"<td>{_escape(_fmt_number(finding.value))}</td>"
            f"<td>{_escape(_fmt_number(finding.threshold))}</td>"
            f"<td>{window}</td>"
            "</tr>"
        )
    return (
        '<section id="alerts">'
        "<h2>Alerts</h2>"
        "<table>"
        "<caption>Rule findings (deterministic)</caption>"
        "<thead><tr>"
        '<th scope="col">Severity</th>'
        '<th scope="col">Dataset / zone</th>'
        '<th scope="col">Rule</th>'
        '<th scope="col">Detail</th>'
        '<th scope="col">Value</th>'
        '<th scope="col">Threshold</th>'
        '<th scope="col">Window</th>'
        "</tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody>"
        "</table>"
        "</section>"
    )


def _coverage_table(summary: DatasetSummary) -> str:
    """Render a dataset's column-coverage table."""
    rows = "".join(
        "<tr>"
        f"<td>{_escape(column)}</td>"
        f"<td>{count}</td>"
        f"<td>{summary.rows}</td>"
        "</tr>"
        for column, count in summary.coverage
    )
    return (
        "<table>"
        "<caption>Column coverage</caption>"
        "<thead><tr>"
        '<th scope="col">Column</th>'
        '<th scope="col">Non-blank</th>'
        '<th scope="col">Total</th>'
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


def _chart_figure(chart: Chart) -> str:
    """Render one embedded-PNG figure."""
    encoded = base64.b64encode(chart.png_path.read_bytes()).decode("ascii")
    return (
        '<figure class="chart">'
        f'<img src="data:image/png;base64,{encoded}" alt="{_escape(chart.alt)}">'
        f"<figcaption>{_escape(chart.title)}</figcaption>"
        "</figure>"
    )


def build_html(
    summaries: Sequence[DatasetSummary],
    charts: dict[str, list[Chart]],
    *,
    title: str,
    generated_at: datetime,
) -> str:
    """Assemble the complete self-contained HTML document.

    Args:
        summaries: Per-dataset statistics.
        charts: Charts keyed by dataset label.
        title: Page title / heading.
        generated_at: Timestamp rendered in the header.

    Returns:
        The HTML document as a string.
    """
    rows_total = sum(summary.rows for summary in summaries)
    all_findings = [finding for summary in summaries for finding in summary.findings]
    critical = sum(1 for finding in all_findings if finding.severity == "critical")
    generated = generated_at.isoformat()

    nav_items = [
        '<li><a href="#overview">Overview</a></li>',
        '<li><a href="#alerts">Alerts</a></li>',
    ]
    for summary in summaries:
        nav_items.append(
            f'<li><a href="#dataset-{_slug(summary.label)}">'
            f"{_escape(summary.label)}</a></li>"
        )

    cards = "".join(_overview_card(summary) for summary in summaries)

    dataset_sections: list[str] = []
    for summary in summaries:
        dataset_charts = charts.get(summary.label, [])
        if dataset_charts:
            figures = "".join(_chart_figure(chart) for chart in dataset_charts)
            chart_block = f'<div class="charts">{figures}</div>'
        else:
            chart_block = (
                '<p class="empty">No chartable metrics in this dataset.</p>'
            )
        shape_note = ""
        if summary.solidity_rows == 0 and all(
            count == 0 for column, count in summary.coverage if column == "extent"
        ):
            shape_note = (
                '<p class="muted">solidity/extent not measurable in this dataset '
                "(blank cells are preserved).</p>"
            )
        dataset_sections.append(
            f'<section id="dataset-{_slug(summary.label)}">'
            f"<h2>{_escape(summary.label)}</h2>"
            f'<p class="muted">Source: {_escape(summary.source)}</p>'
            f"{_coverage_table(summary)}"
            f"{shape_note}"
            f"{chart_block}"
            "</section>"
        )

    return (
        "<!doctype html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_escape(title)}</title>"
        f"<style>{_CSS}</style>"
        "</head>"
        "<body>"
        '<a class="skip" href="#alerts">Skip to alerts</a>'
        '<header class="wrap">'
        f"<h1>{_escape(title)}</h1>"
        '<p class="muted">Generated '
        f'<time datetime="{_escape(generated)}">{_escape(generated)}</time>'
        f" · {len(summaries)} datasets · {rows_total} rows · "
        f"{len(all_findings)} alerts ({critical} critical)</p>"
        '<nav aria-label="Sections"><ul>' + "".join(nav_items) + "</ul></nav>"
        "</header>"
        '<main class="wrap">'
        '<section id="overview">'
        "<h2>Overview</h2>"
        f'<div class="cards">{cards}</div>'
        "</section>"
        + _alerts_section(summaries)
        + "".join(dataset_sections)
        + "</main>"
        '<footer class="wrap">'
        "<p>Deterministic rules over the CSV; thresholds in docs/DASHBOARD.md. "
        "No LLM, no database.</p>"
        "</footer>"
        "</body>"
        "</html>"
    )


def write_dashboard(
    datasets: Sequence[Dataset],
    out_path: Path,
    *,
    now: datetime,
    pipeline_version: str = "unrecorded",
    title: str = "PlantVision — growth dashboard",
    config: RuleConfig | None = None,
) -> DashboardResult:
    """Render the dashboard for ``datasets`` and write it to ``out_path``.

    Args:
        datasets: Labelled CSV stores.
        out_path: Destination HTML path (parent dirs created).
        now: Reference time for rules and the header.
        pipeline_version: Pipeline label for the cm² chart.
        title: Page title.
        config: Optional rule thresholds.

    Returns:
        A :class:`DashboardResult` summary.

    Raises:
        ValueError: For duplicate labels.
        FileNotFoundError: For a missing CSV.
        OSError: If the destination cannot be written.
    """
    labels = [dataset.label for dataset in datasets]
    if len(set(labels)) != len(labels):
        duplicate = next(label for label in labels if labels.count(label) > 1)
        raise ValueError(f"duplicate dataset label: {duplicate}")

    summaries: list[DatasetSummary] = []
    charts_by_label: dict[str, list[Chart]] = {}
    with tempfile.TemporaryDirectory() as temporary:
        temp_dir = Path(temporary)
        for index, dataset in enumerate(datasets):
            rows = load_rows(dataset.csv_path)
            summaries.append(
                summarize(
                    dataset.label, str(dataset.csv_path), rows,
                    now=now, config=config,
                )
            )
            charts_by_label[dataset.label] = render_charts(
                rows,
                temp_dir / f"{index}-{_slug(dataset.label)}",
                label=dataset.label,
                pipeline_version=pipeline_version,
            )
        document = build_html(
            summaries, charts_by_label, title=title, generated_at=now
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(document, encoding="utf-8")
    findings = tuple(
        finding for summary in summaries for finding in summary.findings
    )
    return DashboardResult(
        out_path=out_path,
        datasets=len(summaries),
        rows_total=sum(summary.rows for summary in summaries),
        findings=findings,
        charts=sum(len(charts) for charts in charts_by_label.values()),
    )
