"""CLI tests for scripts/build_report.py and the Gate 1 builder."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from plantvision.analytics.dashboard.build import build_report, load_panels
from plantvision.analytics.dashboard.frames import select_frames
from plantvision.analytics.timeseries import TIMESERIES_COLUMNS

Root = Path(__file__).resolve().parent.parent
NOW = "2026-11-03T12:00:00Z"


def _load_cli():
    """Load scripts/build_report.py without package machinery."""
    spec = importlib.util.spec_from_file_location(
        "build_report", Root / "scripts" / "build_report.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_csv(path: Path, *, offset: int = 0, rows: int = 6) -> None:
    """Write a small synthetic store."""
    start = datetime(2026, 10, 20 + offset, 6, 0, tzinfo=timezone.utc)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TIMESERIES_COLUMNS)
        writer.writeheader()
        for index in range(rows):
            row = {column: "" for column in TIMESERIES_COLUMNS}
            row.update(
                {
                    "sha256": f"{offset:02d}{index:06d}" + "a" * 56,
                    "captured_at": (start + timedelta(minutes=5 * index))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "camera_id": f"cam-{offset}",
                    "zone_id": f"zone-{offset}",
                    "px_per_mm": "4.0",
                    "area_px": str(1000 + offset * 100 + index * 10),
                    "area_cm2": f"{12.0 + index:.3f}",
                    "scale_ok": "true",
                    "quality_flag": "ok",
                    "settings_source": "exif",
                }
            )
            writer.writerow(row)


def _write_config(root: Path) -> tuple[Path, list[Path]]:
    """Write three stores plus the YAML that points at them."""
    stores = []
    for offset in range(3):
        path = root / f"store-{offset}.csv"
        _write_csv(path, offset=offset)
        stores.append(path)
    entries = [
        {
            "id": f"panel-{offset}",
            "label": f"Panel {offset}",
            "crop": "crop",
            "method": "sam2" if offset == 0 else "exg",
            "method_label": "method",
            "pipeline_version": f"p{offset}",
            "csv": str(path),
            "frames_dir": "",
            "masks_dir": "",
            "note": "note",
        }
        for offset, path in enumerate(stores)
    ]
    config = root / "panels.yaml"
    config.write_text(
        yaml.safe_dump({"title": "Synthetic dashboard", "panels": entries}),
        encoding="utf-8",
    )
    return config, stores


def _stdout(capsys) -> list[str]:
    """Return the captured stdout lines."""
    captured = capsys.readouterr()
    return [line for line in captured.out.splitlines() if line.strip()]


def test_cli_writes_report_and_prints_one_json_line(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    config, _stores = _write_config(tmp_path)
    out = tmp_path / "index.html"
    code = cli.main([
        "--panels", str(config), "--out", str(out), "--now", NOW, "--no-frames",
    ])
    lines = _stdout(capsys)
    assert code == 0
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["status"] == "ok"
    assert payload["panels"] == 3
    assert out.is_file()
    assert payload["bytes"] < 1_048_576


def test_cli_default_now_is_data_derived(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    config, _stores = _write_config(tmp_path)
    out = tmp_path / "index.html"
    dump = tmp_path / "payload.json"
    code = cli.main([
        "--panels", str(config), "--out", str(out), "--no-frames",
        "--dump-payload", str(dump),
    ])
    assert code == 0
    _stdout(capsys)
    payload = json.loads(dump.read_text(encoding="utf-8"))
    assert payload["now_source"] == "data"
    assert payload["generated_at"] is None
    assert "as of" in out.read_text(encoding="utf-8")


def test_cli_now_flag_sets_generated_at(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    config, _stores = _write_config(tmp_path)
    out = tmp_path / "index.html"
    dump = tmp_path / "payload.json"
    code = cli.main([
        "--panels", str(config), "--out", str(out), "--now", NOW, "--no-frames",
        "--dump-payload", str(dump),
    ])
    assert code == 0
    _stdout(capsys)
    payload = json.loads(dump.read_text(encoding="utf-8"))
    assert payload["now_source"] == "cli"
    assert payload["generated_at"] is not None
    assert payload["generated_at"].endswith("Z")
    assert payload["now"].endswith("Z")
    assert "generated" in out.read_text(encoding="utf-8")


def test_cli_missing_csv_exits_1(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    config, stores = _write_config(tmp_path)
    stores[0].unlink()
    code = cli.main([
        "--panels", str(config), "--out", str(tmp_path / "index.html"),
        "--now", NOW, "--no-frames",
    ])
    lines = _stdout(capsys)
    assert code == 1
    assert json.loads(lines[0])["status"] == "error"


def test_cli_bad_panels_yaml_exits_1(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    config = tmp_path / "bad.yaml"
    config.write_text("panels: [unclosed", encoding="utf-8")
    out = tmp_path / "index.html"
    code = cli.main(["--panels", str(config), "--out", str(out)])
    assert code == 1
    assert not out.exists()
    assert json.loads(_stdout(capsys)[0])["status"] == "error"


def test_cli_no_frames_flag_skips_images(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    config, _stores = _write_config(tmp_path)
    out = tmp_path / "index.html"
    code = cli.main([
        "--panels", str(config), "--out", str(out), "--now", NOW, "--no-frames",
    ])
    assert code == 0
    payload = json.loads(_stdout(capsys)[0])
    assert payload["frames"] == 0
    assert "data:image/jpeg" not in out.read_text(encoding="utf-8")
    rows = [
        {"sha256": f"sha{index}", "captured_at": f"2026-10-2{index}T00:00:00Z"}
        for index in range(10)
    ]
    index = {f"sha{position}": Path(f"f{position}.jpg") for position in range(10)}
    assert select_frames(rows, index) == select_frames(rows, index)


def test_cli_budget_exceeded_exits_3(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    config, _stores = _write_config(tmp_path)
    out = tmp_path / "index.html"
    code = cli.main([
        "--panels", str(config), "--out", str(out), "--now", NOW,
        "--no-frames", "--max-bytes", "1000",
    ])
    assert code == 3
    assert not out.exists()
    payload = json.loads(_stdout(capsys)[0])
    assert payload["status"] == "error"
    assert payload["bytes"] > 1000


def test_cli_lang_ru_sets_html_lang(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    config, _stores = _write_config(tmp_path)
    out = tmp_path / "index.html"
    code = cli.main([
        "--panels", str(config), "--out", str(out), "--now", NOW,
        "--no-frames", "--lang", "ru",
    ])
    assert code == 0
    _stdout(capsys)
    html = out.read_text(encoding="utf-8")
    assert '<html lang="ru">' in html
    assert "Обзор" in html


def test_payload_budget_gate(tmp_path: Path) -> None:
    config, _stores = _write_config(tmp_path)
    panels = load_panels(config)
    out = tmp_path / "index.html"
    with pytest.raises(ValueError, match="^payload .* exceeds budget"):
        build_report(
            panels,
            out,
            now=datetime(2026, 11, 3, 12, tzinfo=timezone.utc),
            title="T",
            include_frames=False,
            max_json_bytes=1,
        )
    assert not out.exists()


def test_two_builds_identical(tmp_path: Path) -> None:
    config, _stores = _write_config(tmp_path)
    panels = load_panels(config)
    first = tmp_path / "a.html"
    second = tmp_path / "b.html"
    for path in (first, second):
        build_report(
            panels,
            path,
            now=datetime(2026, 11, 3, 12, tzinfo=timezone.utc),
            title="T",
            include_frames=False,
        )
    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(
        second.read_bytes()
    ).hexdigest()
