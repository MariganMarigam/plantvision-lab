"""CLI tests for scripts/build_dashboard.py (loaded via importlib)."""

from __future__ import annotations

import csv
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from plantvision.analytics.timeseries import TIMESERIES_COLUMNS

_ROOT = Path(__file__).resolve().parent.parent


def _load_cli():
    """Load scripts/build_dashboard.py as a module without package machinery."""
    spec = importlib.util.spec_from_file_location(
        "build_dashboard", _ROOT / "scripts" / "build_dashboard.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_dataset(path: Path, n: int = 8) -> None:
    """Write a minimal valid dataset CSV."""
    base = datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)
    rows = []
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
                "area_px": str(1000 + index),
                "area_cm2": "12.5",
                "roi_fraction_pct": "20.0",
                "solidity": "0.7",
                "extent": "0.5",
                "scale_ok": "true",
                "settings_source": "exif",
            }
        )
        rows.append(row)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TIMESERIES_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _payload(capsys) -> dict:
    """Parse the single JSON line printed by the CLI."""
    captured = capsys.readouterr()
    return json.loads(captured.out.strip().splitlines()[-1])


def test_cli_renders_two_datasets(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    _write_dataset(first)
    _write_dataset(second)
    out = tmp_path / "index.html"
    code = cli.main([
        "--dataset", f"alpha={first}",
        "--dataset", f"beta={second}",
        "--out", str(out),
        "--now", "2026-11-01T12:00:00Z",
    ])
    assert code == 0
    assert out.is_file()
    assert _payload(capsys)["datasets"] == 2


def test_cli_rejects_bad_dataset_spec() -> None:
    cli = _load_cli()
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--dataset", "no-equals"])
    assert excinfo.value.code == 2


def test_cli_missing_csv_returns_1(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    code = cli.main([
        "--dataset", f"x={tmp_path / 'missing.csv'}",
        "--out", str(tmp_path / "index.html"),
        "--now", "2026-11-01T12:00:00Z",
    ])
    assert code == 1
    assert _payload(capsys)["status"] == "error"


def test_cli_duplicate_labels_return_1(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    _write_dataset(first)
    _write_dataset(second)
    code = cli.main([
        "--dataset", f"x={first}",
        "--dataset", f"x={second}",
        "--out", str(tmp_path / "index.html"),
        "--now", "2026-11-01T12:00:00Z",
    ])
    assert code == 1
    assert _payload(capsys)["status"] == "error"


def test_cli_now_flag_is_used_in_header(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    source = tmp_path / "a.csv"
    _write_dataset(source)
    out = tmp_path / "index.html"
    code = cli.main([
        "--dataset", f"x={source}",
        "--out", str(out),
        "--now", "2026-11-02T12:00:00Z",
    ])
    assert code == 0
    _payload(capsys)
    assert "2026-11-02T12:00:00" in out.read_text(encoding="utf-8")
