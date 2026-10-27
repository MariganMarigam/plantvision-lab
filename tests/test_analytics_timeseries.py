"""Unit tests: plantvision.analytics.timeseries store/records/formatting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plantvision.analytics.timeseries import (
    TIMESERIES_COLUMNS,
    FrameRecord,
    append_rows,
    format_row,
    load_frame_records,
    read_timeseries,
    run_update,
)
from plantvision.vision.metrics import FrameMeasurement

_ROOT = Path(__file__).resolve().parents[1]
_CONFIG = _ROOT / "configs" / "pipeline.yaml"
_LEGACY_COLUMNS = TIMESERIES_COLUMNS[:15]


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
        "solidity": "0.9000",
        "hull_area_px": "6000.00",
        "hull_area_cm2": "2.400",
        "perimeter_px": "300.00",
        "perimeter_cm": "6.000",
        "ellipse_major_px": "90.00",
        "ellipse_minor_px": "70.00",
        "extent": "0.8000",
        "n_components": "1",
        "experiment_id": "",
        "biosource_id": "",
        "observation_unit_id": "",
        "treatment_id": "",
        "light_regime": "",
        "exposure_s": "",
        "white_balance": "",
        "gain_db": "",
        "settings_source": "",
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


def test_legacy_header_is_migrated_without_appending_rows(tmp_path: Path) -> None:
    """A 15-column store gains the new header and old rows are padded, not lost."""
    store = tmp_path / "metrics" / "timeseries.csv"
    store.parent.mkdir(parents=True)
    legacy = {col: "x" for col in _LEGACY_COLUMNS}
    legacy["sha256"] = "c" * 64
    legacy["captured_at"] = "2026-10-16T10:00:00Z"
    store.write_text(
        ",".join(_LEGACY_COLUMNS) + "\n" + ",".join(legacy[col] for col in _LEGACY_COLUMNS) + "\n",
        encoding="utf-8",
    )
    result = run_update(tmp_path / "no-originals", _CONFIG, store, tmp_path / "out")
    assert result.appended == 0
    assert result.rows_total == 1
    header = store.read_text(encoding="utf-8").splitlines()[0]
    assert header == ",".join(TIMESERIES_COLUMNS)
    rows = read_timeseries(store)
    assert len(rows) == 1
    assert rows[0]["sha256"] == "c" * 64
    for column in TIMESERIES_COLUMNS[len(_LEGACY_COLUMNS):]:
        assert rows[0][column] == ""


def test_new_columns_round_trip_and_crop_id_stays_out(tmp_path: Path) -> None:
    """Trait + provenance columns survive a write/read; crop_id is not a column."""
    store = tmp_path / "timeseries.csv"
    record = FrameRecord(
        jpg=tmp_path / "frame_a.jpg",
        sha256="d" * 64,
        captured_at="2026-10-16T10:00:00Z",
        received_at="2026-10-16T10:00:01Z",
        camera_id="cam-a",
        zone_id="z",
        width=400,
        height=400,
        experiment_id="basil-2026-10",
        biosource_id="basil-genovese",
        observation_unit_id="z/slot-1",
        treatment_id="led-white-18h",
        light_regime="white-18/6",
        exposure_s=0.02,
        white_balance="auto",
        gain_db=None,
        settings_source="exif",
    )
    meas = _measurement(
        px_per_mm=5.0,
        hull_area_px=9801.0,
        solidity=1.0,
        perimeter_px=396.0,
        ellipse_major_px=100.0,
        ellipse_minor_px=100.0,
        extent=0.9801,
        n_components=1,
    )
    append_rows(store, [format_row(record, meas)])
    rows = read_timeseries(store)
    assert len(rows) == 1
    row = rows[0]
    assert row["solidity"] == "1.0000"
    assert row["hull_area_px"] == "9801.00"
    assert row["hull_area_cm2"] == "3.920"   # 9801 / 5^2 / 100
    assert row["perimeter_cm"] == "7.920"    # 396 / 5 / 10
    assert row["ellipse_major_px"] == "100.00"
    assert row["extent"] == "0.9801"
    assert row["n_components"] == "1"
    assert row["experiment_id"] == "basil-2026-10"
    assert row["exposure_s"] == "0.0200"
    assert row["white_balance"] == "auto"
    assert row["gain_db"] == ""
    assert row["settings_source"] == "exif"
    assert "crop_id" not in TIMESERIES_COLUMNS
    assert "crop_id" not in row


def test_format_row_empty_mask_keeps_trait_cells_blank(tmp_path: Path) -> None:
    """No mask: every trait cell is blank (never 0, nan or inf)."""
    row = format_row(_record(tmp_path), _measurement())
    trait_columns = (
        "solidity", "hull_area_px", "hull_area_cm2", "perimeter_px", "perimeter_cm",
        "ellipse_major_px", "ellipse_minor_px", "extent", "n_components",
    )
    assert all(row[column] == "" for column in trait_columns)
    assert "nan" not in ",".join(row.values()).lower()
    assert "inf" not in ",".join(row.values()).lower()


_PROVENANCE_COLUMNS = TIMESERIES_COLUMNS[-9:]


def _write_sidecar_pair(folder: Path, sidecar: dict) -> None:
    """Write one jpg + JSON sidecar pair under ``folder``."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "frame.jpg").write_bytes(b"\xff\xd8fakejpg")
    (folder / "frame.json").write_text(json.dumps(sidecar), encoding="utf-8")


def test_legacy_sidecar_yields_nine_blank_provenance_cells(tmp_path: Path) -> None:
    """A pre-P1.5 sidecar (7 keys) loads without error and fills no provenance."""
    _write_sidecar_pair(tmp_path, {
        "sha256": "e" * 64,
        "captured_at": "2026-10-16T10:00:00Z",
        "camera_id": "cam-a",
        "zone_id": "z",
        "width": 400,
        "height": 400,
        "received_at": "2026-10-16T10:00:01Z",
    })
    records = load_frame_records(tmp_path)
    assert len(records) == 1
    row = format_row(records[0], _measurement())
    assert all(row[column] == "" for column in _PROVENANCE_COLUMNS)


def test_full_sidecar_provenance_round_trips(tmp_path: Path) -> None:
    """A sidecar with all nine provenance keys reaches the CSV unchanged."""
    _write_sidecar_pair(tmp_path, {
        "sha256": "f" * 64,
        "captured_at": "2026-10-16T10:00:00Z",
        "camera_id": "cam-a",
        "zone_id": "z",
        "width": 400,
        "height": 400,
        "received_at": "2026-10-16T10:00:01Z",
        "experiment_id": "basil-2026-10",
        "biosource_id": "basil-genovese",
        "observation_unit_id": "z/slot-1",
        "treatment_id": "led-white-18h",
        "light_regime": "white-18/6",
        "exposure_s": 0.02,
        "white_balance": "auto",
        "gain_db": None,
        "settings_source": "exif",
    })
    row = format_row(load_frame_records(tmp_path)[0], _measurement())
    assert row["experiment_id"] == "basil-2026-10"
    assert row["biosource_id"] == "basil-genovese"
    assert row["observation_unit_id"] == "z/slot-1"
    assert row["treatment_id"] == "led-white-18h"
    assert row["light_regime"] == "white-18/6"
    assert row["exposure_s"] == "0.0200"
    assert row["white_balance"] == "auto"
    assert row["gain_db"] == ""
    assert row["settings_source"] == "exif"


def test_explicit_null_provenance_is_blank(tmp_path: Path) -> None:
    """JSON null and an absent key both become an empty CSV cell."""
    _write_sidecar_pair(tmp_path, {
        "sha256": "1" * 64,
        "captured_at": "2026-10-16T10:00:00Z",
        "camera_id": "cam-a",
        "zone_id": "z",
        "width": 400,
        "height": 400,
        "received_at": "2026-10-16T10:00:01Z",
        "experiment_id": None,
        "exposure_s": None,
        "settings_source": None,
    })
    row = format_row(load_frame_records(tmp_path)[0], _measurement())
    assert row["experiment_id"] == ""
    assert row["exposure_s"] == ""
    assert row["settings_source"] == ""


def test_setting_without_settings_source_raises(tmp_path: Path) -> None:
    """A recorded exposure without provenance is a false claim."""
    _write_sidecar_pair(tmp_path, {
        "sha256": "2" * 64,
        "captured_at": "2026-10-16T10:00:00Z",
        "camera_id": "cam-a",
        "zone_id": "z",
        "width": 400,
        "height": 400,
        "received_at": "2026-10-16T10:00:01Z",
        "exposure_s": 0.02,
    })
    with pytest.raises(ValueError, match="settings_source"):
        load_frame_records(tmp_path)


def test_foreign_header_raises_naming_both(tmp_path: Path) -> None:
    """A header that is neither exact nor a strict prefix is rejected."""
    store = tmp_path / "timeseries.csv"
    store.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header mismatch"):
        append_rows(store, [])
    assert store.read_text(encoding="utf-8") == "a,b\n1,2\n"
