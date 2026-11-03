"""Dashboard: legacy PNG renderer (:mod:`.legacy`) and the v2 HTML shell."""

from __future__ import annotations

from .legacy import (
    Chart,
    DashboardResult,
    Dataset,
    DatasetSummary,
    _alerts_section,
    _overview_card,
    _split_runs,
    build_html,
    load_rows,
    render_charts,
    render_series_chart,
    render_shape_chart,
    summarize,
    write_dashboard,
)

__all__ = [
    "Chart",
    "DashboardResult",
    "Dataset",
    "DatasetSummary",
    "build_html",
    "load_rows",
    "render_charts",
    "render_series_chart",
    "render_shape_chart",
    "summarize",
    "write_dashboard",
]

from .build import Panel, ReportResult, build_report, load_panels

__all__ += ["Panel", "ReportResult", "build_report", "load_panels"]
