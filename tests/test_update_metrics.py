"""Integration tests: scripts/update_metrics.py end-to-end on synthetic frames."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np

from plantvision.analytics.timeseries import (
    TIMESERIES_COLUMNS,
    read_timeseries,
    run_update,
)

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG = _ROOT / "configs" / "pipeline.yaml"


def _load_script():
    """Load scripts/update_metrics.py as a module without package machinery."""
    spec = importlib.util.spec_from_file_location(
        "update_metrics", _ROOT / "scripts" / "update_metrics.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_frame(
    folder: Path, name: str, captured_at: str, with_marker: bool, sha: str | None = None
) -> None:
    """Write one 400x400 synthetic frame (green circle, optional marker) + sidecar."""
    folder.mkdir(parents=True, exist_ok=True)
    canvas = np.full((400, 400, 3), 255, np.uint8)
    cv2.circle(canvas, (250, 250), 40, (0, 200, 0), -1)
    if with_marker:
        m = cv2.aruco.generateImageMarker(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50), 1, 200
        )
        canvas[10:210, 10:210] = cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)
    cv2.imwrite(str(folder / f"{name}.jpg"), canvas)
    sidecar = {
        "sha256": sha if sha is not None else name[:16].ljust(16, "0"),
        "captured_at": captured_at,
        "camera_id": "cam-a",
        "zone_id": "z",
        "width": 400,
        "height": 400,
        "byte_size": 1,
        "quality": "ok",
        "received_at": captured_at,
    }
    (folder / f"{name}.json").write_text(json.dumps(sidecar), encoding="utf-8")


def _write_unreadable(folder: Path, name: str, captured_at: str) -> None:
    """Write a non-image .jpg with a valid sidecar (decode must fail per-frame)."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.jpg").write_bytes(b"not an image at all")
    sidecar = {
        "sha256": name[:16].ljust(16, "0"),
        "captured_at": captured_at,
        "camera_id": "cam-a",
        "zone_id": "z",
        "width": 400,
        "height": 400,
        "byte_size": 19,
        "quality": "ok",
        "received_at": captured_at,
    }
    (folder / f"{name}.json").write_text(json.dumps(sidecar), encoding="utf-8")


def _default_paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """(originals, config, store, out) under tmp_path."""
    originals = tmp_path / "originals"
    store = tmp_path / "metrics" / "timeseries.csv"
    out = tmp_path / "metrics"
    return originals, _CONFIG, store, out


def test_update_measures_new_frames_and_appends(tmp_path: Path) -> None:
    """Two new frames (marker + no-marker) -> 2 rows with correct flags."""
    originals, config, store, out = _default_paths(tmp_path)
    day = originals / "cam-a" / "z" / "2026-10-16"
    _write_frame(day, "frame_a", "2026-10-16T10:00:00Z", with_marker=True)
    _write_frame(day, "frame_b", "2026-10-16T10:01:00Z", with_marker=False)
    result = run_update(originals, config, store, out)
    assert result.appended == 2
    assert result.measured == 2
    assert result.errors == 0
    rows = read_timeseries(store)
    assert len(rows) == 2
    header = store.read_text(encoding="utf-8").splitlines()[0]
    assert header == ",".join(TIMESERIES_COLUMNS)
    by_sha = {r["sha256"]: r for r in rows}
    marker_row = by_sha["frame_a".ljust(16, "0")]
    nomark_row = by_sha["frame_b".ljust(16, "0")]
    assert marker_row["area_cm2"] != "" and marker_row["scale_ok"] == "true"
    assert nomark_row["area_cm2"] == "" and nomark_row["scale_ok"] == "false"


def test_update_idempotent_run_twice(tmp_path: Path) -> None:
    """Second pass over the same originals appends 0 rows."""
    originals, config, store, out = _default_paths(tmp_path)
    day = originals / "cam-a" / "z" / "2026-10-16"
    _write_frame(day, "frame_a", "2026-10-16T10:00:00Z", with_marker=True)
    _write_frame(day, "frame_b", "2026-10-16T10:01:00Z", with_marker=False)
    first = run_update(originals, config, store, out)
    second = run_update(originals, config, store, out)
    assert first.appended == 2
    assert second.appended == 0
    assert second.skipped == 2
    assert len(read_timeseries(store)) == 2


def test_update_skips_corrupt_sidecar(tmp_path: Path) -> None:
    """A frame with a malformed sidecar never reaches the store."""
    originals, config, store, out = _default_paths(tmp_path)
    day = originals / "cam-a" / "z" / "2026-10-16"
    _write_frame(day, "frame_good", "2026-10-16T10:00:00Z", with_marker=True)
    (day / "frame_bad.jpg").write_bytes(b"\xff\xd8fakejpg")
    (day / "frame_bad.json").write_text("not json", encoding="utf-8")
    result = run_update(originals, config, store, out)
    assert result.scanned == 1
    assert result.appended == 1
    rows = read_timeseries(store)
    assert [r["sha256"] for r in rows] == ["frame_good".ljust(16, "0")]


def test_update_non_fatal_on_unreadable_jpg(tmp_path: Path) -> None:
    """An undecodable jpg increments errors; the valid frame is still stored."""
    originals, config, store, out = _default_paths(tmp_path)
    day = originals / "cam-a" / "z" / "2026-10-16"
    _write_frame(day, "frame_good", "2026-10-16T10:00:00Z", with_marker=True)
    _write_unreadable(day, "frame_broken", "2026-10-16T10:01:00Z")
    result = run_update(originals, config, store, out)
    assert result.errors >= 1
    assert result.appended == 1
    rows = read_timeseries(store)
    assert [r["sha256"] for r in rows] == ["frame_good".ljust(16, "0")]


def test_update_regenerates_plot(tmp_path: Path) -> None:
    """The run writes one projected-area PNG per zone, readable by cv2."""
    originals, config, store, out = _default_paths(tmp_path)
    day = originals / "cam-a" / "z" / "2026-10-16"
    _write_frame(day, "frame_a", "2026-10-16T10:00:00Z", with_marker=True)
    run_update(originals, config, store, out)
    png = out / "projected-area-z.png"
    assert png.exists()
    assert cv2.imread(str(png)) is not None


def test_update_empty_originals_is_noop(tmp_path: Path) -> None:
    """An empty originals tree appends nothing and plots nothing."""
    originals, config, store, out = _default_paths(tmp_path)
    originals.mkdir(parents=True)
    result = run_update(originals, config, store, out)
    assert result.measured == 0
    assert result.appended == 0
    assert result.plot_paths == ()


def test_main_returns_zero_with_frame_errors(tmp_path: Path, capsys) -> None:
    """Per-frame errors are non-fatal: exit 0 with status ok in the JSON summary."""
    originals, config, store, out = _default_paths(tmp_path)
    day = originals / "cam-a" / "z" / "2026-10-16"
    _write_unreadable(day, "frame_broken", "2026-10-16T10:00:00Z")
    mod = _load_script()
    rc = mod.main(
        [
            "--originals", str(originals),
            "--config", str(config),
            "--store", str(store),
            "--out", str(out),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["errors"] >= 1
