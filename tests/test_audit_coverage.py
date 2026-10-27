"""Tests for scripts/audit_coverage.py (P1.5.3)."""

from __future__ import annotations

import csv
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_COLUMNS = ("sha256", "captured_at", "zone_id", "quality_flag", "scale_ok", "settings_source")


def _load_script():
    """Load scripts/audit_coverage.py as a module without package machinery."""
    spec = importlib.util.spec_from_file_location(
        "audit_coverage", _ROOT / "scripts" / "audit_coverage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stamp(moment: datetime) -> str:
    """ISO-8601 UTC Z timestamp (no microseconds)."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _full_day(zone: str = "z") -> list[dict[str, str]]:
    """24 h at 5 min = 288 rows, all with a unique sha256 and explicit settings."""
    base = datetime(2026, 10, 13, 0, 0, tzinfo=timezone.utc)
    rows: list[dict[str, str]] = []
    for index in range(288):
        rows.append({
            "sha256": f"{index:064x}",
            "captured_at": _stamp(base + timedelta(minutes=5 * index)),
            "zone_id": zone,
            "quality_flag": "ok",
            "scale_ok": "true",
            "settings_source": "exif",
        })
    return rows


def _write_store(path: Path, rows: list[dict[str, str]]) -> None:
    """Write rows with the audit's minimal column set."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def _drop(rows: list[dict[str, str]], stamps: set[str]) -> list[dict[str, str]]:
    """Return rows without the given timestamps."""
    return [row for row in rows if row["captured_at"] not in stamps]


def _run(tmp_path: Path, rows: list[dict[str, str]], *extra: str) -> tuple[int, dict[str, Any], str]:
    """Write a store, run the CLI, and return (exit code, JSON report, markdown)."""
    store = tmp_path / "timeseries.csv"
    out = tmp_path / "coverage.md"
    report_path = tmp_path / "coverage.json"
    _write_store(store, rows)
    code = _load_script().main([
        "--csv", str(store), "--cadence-min", "5",
        "--dark-start", "22:00", "--dark-end", "06:00",
        "--max-missing", "24", "--max-gap-min", "60",
        "--out", str(out), "--json", str(report_path), *extra,
    ])
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    return code, report, out.read_text(encoding="utf-8")


def test_three_missing_lit_slots_and_15_minute_gap(tmp_path: Path) -> None:
    """Two consecutive holes + one isolated hole give missing=3, gap=15."""
    rows = _drop(_full_day(), {"2026-10-13T12:00:00Z", "2026-10-13T12:05:00Z",
                               "2026-10-13T18:00:00Z"})
    code, report, _text = _run(tmp_path, rows)
    zone = report["zones"][0]
    assert code == 0
    assert zone["expected_slots"] == 288
    assert zone["present"] == 285
    assert zone["missing"] == 3
    assert zone["longest_gap_minutes"] == 15.0
    assert zone["longest_gap_start"] == "2026-10-13T11:55:00Z"
    assert zone["longest_gap_end"] == "2026-10-13T12:10:00Z"


def test_missing_dark_slot_is_outside_policy_not_missing(tmp_path: Path) -> None:
    """A hole inside [22:00, 06:00) is expected darkness, not a data gap."""
    rows = _drop(_full_day(), {"2026-10-13T23:00:00Z"})
    code, report, _text = _run(tmp_path, rows)
    zone = report["zones"][0]
    assert code == 0
    assert zone["outside_dark_policy"] == 1
    assert zone["missing"] == 0


def test_duplicate_sha_is_reported_without_changing_coverage(tmp_path: Path) -> None:
    """A repeated sha256/row adds one duplicate and collapses to one slot."""
    rows = _full_day()
    rows.append(dict(rows[0]))
    code, report, _text = _run(tmp_path, rows)
    zone = report["zones"][0]
    assert code == 0
    assert zone["duplicates"] == 1
    assert zone["present"] == 288
    assert zone["missing"] == 0
    assert zone["duplicate_timestamps"] == 1


def test_missing_threshold_exit_codes(tmp_path: Path) -> None:
    """missing=3 fails --max-missing 2 (exit 2) and passes --max-missing 3."""
    rows = _drop(_full_day(), {"2026-10-13T12:00:00Z", "2026-10-13T12:05:00Z",
                               "2026-10-13T18:00:00Z"})
    strict, _report, _text = _run(tmp_path, rows, "--max-missing", "2")
    exact, _report2, _text2 = _run(tmp_path / "exact", rows, "--max-missing", "3")
    assert strict == 2
    assert exact == 0


def test_fewer_than_two_rows_is_insufficient_data(tmp_path: Path) -> None:
    """One row cannot define a cadence grid; report it and exit 0."""
    code, report, text = _run(tmp_path, _full_day()[:1])
    assert code == 0
    assert report["zones"][0]["status"] == "insufficient data"
    assert "insufficient data" in text


def test_empty_store_is_no_rows(tmp_path: Path) -> None:
    """An empty CSV is a clean no-data report, exit 0."""
    code, _report, text = _run(tmp_path, [])
    assert code == 0
    assert "no rows" in text


def test_unsorted_and_unparseable_timestamps_do_not_crash(tmp_path: Path) -> None:
    """Sorting is internal; a bad timestamp is counted as undated."""
    rows = list(reversed(_full_day()[:10]))
    rows.append({"sha256": "x" * 64, "captured_at": "not-a-time", "zone_id": "z",
                 "quality_flag": "ok", "scale_ok": "true", "settings_source": "exif"})
    code, report, _text = _run(tmp_path, rows)
    zone = report["zones"][0]
    assert code == 0
    assert zone["undated"] == 1
    assert zone["missing"] == 0
