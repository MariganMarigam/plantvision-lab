"""Unit tests: plantvision.analytics.timeseries store/records/formatting."""

from __future__ import annotations

import json
from pathlib import Path

from plantvision.analytics.timeseries import (
    TIMESERIES_COLUMNS,
    FrameRecord,
    append_rows,
    format_row,
    load_frame_records,
    read_timeseries,
)
from plantvision.vision.metrics import FrameMeasurement


def _write_frame(
    folder: Path, name: str, captured_at: str | None, sha: str | None = None
) -> None:
    """Write a minimal jpg + sidecar pair (bytes irrelevant for record loading)."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.jpg").write_bytes(b"\xff\xd8fakejpg")
    sidecar: dict = {
        "sha256": sha if sha is not None else name[:16].ljust(16, "0"),
        "camera_id": "cam-a",
        "zone_id": "z",
        "width": 400,
        "height": 400,
        "byte_size": 1,
        "quality": "ok",
        "received_at": captured_at,
    }
    if captured_at is not None:
        sidecar["captured_at"] = captured_at
    (folder / f"{name}.json").write_text(json.dumps(sidecar), encoding="utf-8")


def _full_row(sha: str) -> dict[str, str]:
    """One complete store row keyed exactly by TIMESERIES_COLUMNS."""
    values = {
        "sha256": sha,
        "captured_at": "2026-10-16T10:00:00Z",
        "received_at": "2026-10-16T10:00:01Z",
        "camera_id": "cam-a",
        "zone_id": "z",
        "width": "400",
        "height": "400",
        "px_per_mm": "5.1235",
        "area_px": "5027",
        "area_cm2": "4.988",
        "roi_fraction_pct": "3.142",
        "bbox_w": "80",
        "bbox_h": "80",
        "quality_flag": "",
        "scale_ok": "true",
    }
    return {col: values[col] for col in TIMESERIES_COLUMNS}


def _measurement(**overrides) -> FrameMeasurement:
    """A FrameMeasurement with per-test overrides."""
    fields = {
        "stem": "frame_a",
        "captured_at": "2026-10-16T10:00:00Z",
        "px_per_mm": 5.123456,
        "projected_area_px": 5027,
        "projected_area_cm2": 4.9876543,
        "roi_fraction_pct": 3.1416,
        "bbox_w": 80,
        "bbox_h": 80,
        "bbox_w_cm": 1.5615,
        "bbox_h_cm": 1.5615,
        "blur_lapvar": 16.2,
        "brightness_mean": 128.4,
        "quality_flags": (),
    }
    fields.update(overrides)
    return FrameMeasurement(**fields)


def _record(tmp_path: Path) -> FrameRecord:
    """A FrameRecord pointing at a synthetic jpg."""
    return FrameRecord(
        jpg=tmp_path / "frame_a.jpg",
        sha256="a" * 64,
        captured_at="2026-10-16T10:00:00Z",
        received_at="2026-10-16T10:00:01Z",
        camera_id="cam-a",
        zone_id="z",
        width=400,
        height=400,
    )


def test_load_frame_records_reads_sidecar_metadata(tmp_path: Path) -> None:
    """sha256/timestamps/camera/zone/dimensions come from the sidecar."""
    _write_frame(tmp_path / "cam-a" / "z" / "2026-10-16", "frame_a", "2026-10-16T10:00:00Z")
    records = load_frame_records(tmp_path)
    assert len(records) == 1
    rec = records[0]
    assert rec.sha256 == "frame_a".ljust(16, "0")
    assert rec.captured_at == "2026-10-16T10:00:00Z"
    assert rec.received_at == "2026-10-16T10:00:00Z"
    assert rec.camera_id == "cam-a"
    assert rec.zone_id == "z"
    assert rec.width == 400
    assert rec.height == 400
    assert rec.jpg.name == "frame_a.jpg"


def test_load_frame_records_skips_missing_sidecar(tmp_path: Path) -> None:
    """A .jpg with no .json yields no record."""
    folder = tmp_path / "cam-a" / "z" / "2026-10-16"
    folder.mkdir(parents=True)
    (folder / "orphan.jpg").write_bytes(b"\xff\xd8fakejpg")
    assert load_frame_records(tmp_path) == []


def test_load_frame_records_skips_malformed_sidecar(tmp_path: Path) -> None:
    """A .json containing 'not json' yields no record; no exception."""
    folder = tmp_path / "cam-a" / "z" / "2026-10-16"
    folder.mkdir(parents=True)
    (folder / "bad.jpg").write_bytes(b"\xff\xd8fakejpg")
    (folder / "bad.json").write_text("not json", encoding="utf-8")
    assert load_frame_records(tmp_path) == []


def test_load_frame_records_sorted_chronologically(tmp_path: Path) -> None:
    """Order is (captured_at is None, captured_at, name): unknown timestamps last."""
    folder = tmp_path / "cam-a" / "z" / "2026-10-16"
    _write_frame(folder, "frame_b", "2026-10-16T10:01:00Z")
    _write_frame(folder, "frame_a2", "2026-10-16T10:00:00Z")
    _write_frame(folder, "frame_a1", "2026-10-16T10:00:00Z")
    _write_frame(folder, "frame_z9", None)
    records = load_frame_records(tmp_path)
    assert [r.jpg.name for r in records] == [
        "frame_a1.jpg", "frame_a2.jpg", "frame_b.jpg", "frame_z9.jpg",
    ]


def test_read_timeseries_missing_file_returns_empty(tmp_path: Path) -> None:
    """Non-existent store path reads as no rows."""
    assert read_timeseries(tmp_path / "missing.csv") == []


def test_append_rows_writes_header_then_appends(tmp_path: Path) -> None:
    """First append writes header + 1 row; second appends (header written ONCE)."""
    store = tmp_path / "metrics" / "timeseries.csv"
    assert append_rows(store, [_full_row("a" * 64)]) == 1
    assert append_rows(store, [_full_row("b" * 64)]) == 1
    lines = store.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(TIMESERIES_COLUMNS)
    assert sum(1 for ln in lines if ln.startswith("sha256,")) == 1
    assert len(read_timeseries(store)) == 2


def test_append_rows_empty_is_noop(tmp_path: Path) -> None:
    """Appending nothing returns 0 and creates no file."""
    store = tmp_path / "metrics" / "timeseries.csv"
    assert append_rows(store, []) == 0
    assert not store.exists()


def test_format_row_no_marker_is_flagged_not_dropped(tmp_path: Path) -> None:
    """No marker: area_cm2 empty, scale_ok false, quality flags preserved."""
    meas = _measurement(
        px_per_mm=None,
        projected_area_cm2=None,
        bbox_w_cm=None,
        bbox_h_cm=None,
        quality_flags=("blur", "dark"),
    )
    row = format_row(_record(tmp_path), meas)
    assert set(row) == set(TIMESERIES_COLUMNS)
    assert row["area_cm2"] == ""
    assert row["px_per_mm"] == ""
    assert row["scale_ok"] == "false"
    assert row["quality_flag"] == "blur|dark"
    assert row["sha256"] == "a" * 64


def test_format_row_with_marker(tmp_path: Path) -> None:
    """With a marker: scale_ok true, area 3 dp, px_per_mm 4 dp."""
    row = format_row(_record(tmp_path), _measurement())
    assert row["scale_ok"] == "true"
    assert row["area_cm2"] == "4.988"
    assert row["px_per_mm"] == "5.1235"
    assert row["area_px"] == "5027"
    assert row["roi_fraction_pct"] == "3.142"
