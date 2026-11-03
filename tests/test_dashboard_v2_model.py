"""Payload/transform tests for the v2 dashboard model."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from plantvision.analytics import dashboard as legacy_pkg
from plantvision.analytics.dashboard import model
from plantvision.analytics.dashboard.model import (
    build_payload,
    build_series,
    calendar_payload,
    comparison_payload,
    coverage_block,
    daily_buckets,
    panel_payload,
    quality_block,
    split_runs,
    stats,
)
from plantvision.analytics.timeseries import TIMESERIES_COLUMNS

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
UTC = timezone.utc


@dataclass(frozen=True)
class FakePanel:
    """Duck-typed stand-in for build.Panel."""

    id: str
    label: str
    crop: str = "crop"
    method: str = "sam2"
    method_label: str = "method"
    pipeline_version: str = "p1"
    note: str = ""
    csv_path: Path = Path("unused.csv")
    frames_dir: Path | None = None
    masks_dir: Path | None = None


def _ts(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _row(**values: str) -> dict[str, str]:
    row = {column: "" for column in TIMESERIES_COLUMNS}
    row.update(values)
    return row


def _series_rows(count: int, *, start: datetime, step_minutes: int = 5) -> list[dict[str, str]]:
    rows = []
    for index in range(count):
        rows.append(
            _row(
                sha256=f"sha{index:04d}",
                captured_at=_ts(start + timedelta(minutes=step_minutes * index)),
                camera_id="cam",
                zone_id="z",
                area_px=str(1000 + index),
                area_cm2="12.5",
                scale_ok="true",
                settings_source="exif",
            )
        )
    return rows


def test_split_runs_matches_legacy() -> None:
    base = datetime(2026, 10, 1, tzinfo=UTC)
    cases = []
    for count in (0, 1, 2, 3, 7, 12):
        points = [
            (base + timedelta(minutes=5 * index), float(index))
            for index in range(count)
        ]
        cases.append(points)
    for count, gap in ((6, 30), (6, 180), (10, 900), (4, 5), (5, 2), (8, 1)):
        points = [
            (base + timedelta(minutes=5 * index), float(index))
            for index in range(count)
        ]
        points.append((base + timedelta(minutes=5 * count + gap), 99.0))
        cases.append(points)
    for points in cases:
        assert split_runs(points) == legacy_pkg._split_runs(points)


def test_series_blank_cells_are_missing_not_zero() -> None:
    rows = _series_rows(8, start=datetime(2026, 10, 1, tzinfo=UTC))
    for row in rows[:3]:
        row["area_cm2"] = ""
    series = build_series(rows, "area_cm2", unit="cm²", decimals=2)
    assert series.measured == 5
    assert series.missing == 3
    assert series.stats is not None
    assert series.stats["n"] == 5


def test_downsample_caps_total_points_at_240() -> None:
    rows = _series_rows(681, start=datetime(2026, 10, 1, tzinfo=UTC))
    series = build_series(rows, "area_px", unit="px", decimals=0)
    assert sum(len(run) for run in series.runs) <= 240
    assert series.downsampled is True
    assert series.measured == 681


def test_downsample_keeps_min_and_max_per_bucket() -> None:
    rows = _series_rows(1000, start=datetime(2026, 10, 1, tzinfo=UTC))
    rows[500]["area_px"] = "999999"
    rows[501]["area_px"] = "-5000"
    series = build_series(rows, "area_px", unit="px", decimals=0)
    kept = [value for run in series.runs for _ts_ms, value in run]
    assert max(kept) == 999999.0
    assert min(kept) == -5000.0


def test_downsample_never_merges_runs_across_gap() -> None:
    start = datetime(2026, 10, 1, tzinfo=UTC)
    rows = _series_rows(40, start=start)
    rows += _series_rows(40, start=start + timedelta(hours=16))
    series = build_series(rows, "area_px", unit="px", decimals=0)
    assert len(series.runs) == 2
    assert series.gaps


def test_stats_ignore_missing_values() -> None:
    rows = _series_rows(7, start=datetime(2026, 10, 1, tzinfo=UTC))
    for row in rows[::2]:
        row["area_px"] = ""
    series = build_series(rows, "area_px", unit="px", decimals=0)
    values = [1000.0 + index for index in range(7) if index % 2 == 1]
    assert series.stats is not None
    assert series.stats["median"] == sorted(values)[len(values) // 2]
    assert stats(values) == series.stats


def test_daily_buckets_are_utc_days() -> None:
    rows = [
        _row(captured_at="2026-10-24T23:30:00Z", area_px="10", scale_ok="true"),
        _row(captured_at="2026-10-25T00:30:00Z", area_px="20", scale_ok="true"),
    ]
    buckets = daily_buckets(rows)
    assert [bucket["date"] for bucket in buckets] == ["2026-10-24", "2026-10-25"]
    assert buckets[0]["frames"] == 1


def test_quality_rate_is_none_when_column_blank() -> None:
    rows = _series_rows(4, start=datetime(2026, 10, 1, tzinfo=UTC))
    block = quality_block(rows)
    assert block["measured"] is False
    assert block["rate_pct"] is None


def test_coverage_counts_non_blank_cells() -> None:
    rows = _series_rows(3, start=datetime(2026, 10, 1, tzinfo=UTC))
    rows[0]["solidity"] = "0.6"
    rows[1]["solidity"] = "0.5"
    block = coverage_block(rows)
    assert len(block) == len(TIMESERIES_COLUMNS)
    by_column = {item["column"]: item for item in block}
    assert by_column["area_px"]["measured"] == 3
    assert by_column["solidity"]["measured"] == 2
    assert by_column["n_components"]["measured"] == 0


def test_comparison_index_starts_at_100() -> None:
    start = datetime(2026, 10, 1, tzinfo=UTC)
    panels = []
    for index, step in ((0, 10), (1, 100)):
        rows = _series_rows(3, start=start + timedelta(hours=index))
        for offset, row in enumerate(rows):
            row["area_px"] = str(step * (offset + 1))
        payload = panel_payload(
            FakePanel(id=f"p{index}", label=f"P{index}"), rows, now=NOW
        )
        panels.append(payload)
    comparison = comparison_payload(panels)
    assert comparison["excluded"] == []
    for item in comparison["series"]:
        assert item["points"][0] == [0.0, 100.0]


def test_calendar_covers_every_day_in_range() -> None:
    panels = []
    for index, (first, last) in enumerate(
        (("2026-10-16T09:00:00Z", "2026-11-01T09:00:00Z"), ("2026-10-20T09:00:00Z", "2026-10-21T09:00:00Z"))
    ):
        rows = [
            _row(captured_at=first, area_px="10", scale_ok="true"),
            _row(captured_at=last, area_px="20", scale_ok="true"),
        ]
        panels.append(
            panel_payload(FakePanel(id=f"p{index}", label=f"P{index}"), rows, now=NOW)
        )
    calendar = calendar_payload(panels)
    assert calendar["start"] == "2026-10-16"
    assert calendar["end"] == "2026-11-01"
    for row in calendar["rows"]:
        assert len(row["cells"]) == 17


def test_payload_is_deterministic_for_fixed_now(tmp_path: Path) -> None:
    panels = []
    for index in range(3):
        path = tmp_path / f"store{index}.csv"
        rows = _series_rows(6, start=datetime(2026, 10, 1 + index, tzinfo=UTC))
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TIMESERIES_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        panels.append(FakePanel(id=f"p{index}", label=f"P{index}", csv_path=path))
    first = build_payload(panels, now=NOW, title="T")
    second = build_payload(panels, now=NOW, title="T")
    dump = lambda payload: json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert dump(first) == dump(second)
    assert first["totals"]["panels"] == 3
    assert first["now_source"] == "cli"
