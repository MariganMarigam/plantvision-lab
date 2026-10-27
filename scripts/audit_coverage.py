"""Coverage audit for the PlantVision time-series store (P1.5.3).

Makes "no data" distinguishable from "no change": groups stored rows by zone,
builds the expected capture grid at ``--cadence-min``, and classifies every
slot as present, missing, or outside the dark policy. Reports duplicates, the
longest gap, quality/scale flags and unknown camera settings per zone.

Exit codes: 0 = ok, 2 = a threshold was exceeded, 1 = usage/IO error.
Dependencies: Python standard library only (``csv``/``datetime``/``argparse``).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Sequence

_SCRIPT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG = _SCRIPT_ROOT / "configs" / "capture-farm.yaml"

_HEADER = (
    "| zone | rows | expected | present | missing | outside_dark_policy | undated | "
    "duplicates | longest_gap_min | gap_start | gap_end | quality_bad | scale_false | "
    "settings_unknown | status |"
)
_SEPARATOR = "|" + "---|" * 15


class _Parser(argparse.ArgumentParser):
    """Argument parser that maps usage errors to exit code 1 (not argparse's 2)."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        raise SystemExit(1)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments (dark-window defaults come from the farm config)."""
    parser = _Parser(description="Audit capture coverage of the metrics time-series store.")
    parser.add_argument("--csv", default="data/derived/timeseries.csv")
    parser.add_argument("--cadence-min", type=int, default=5)
    parser.add_argument("--dark-start", default=None, help="HH:MM; defaults to farm config")
    parser.add_argument("--dark-end", default=None, help="HH:MM; defaults to farm config")
    parser.add_argument("--max-missing", type=int, default=24)
    parser.add_argument("--max-gap-min", type=float, default=60.0)
    parser.add_argument("--out", default="data/derived/coverage.md")
    parser.add_argument(
        "--json", nargs="?", const="", default=None,
        help="Also write a JSON report (default path: <out>.json).",
    )
    return parser.parse_args(argv)


def _parse_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (``Z`` or offset) to aware UTC; else None."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_clock(value: str | None) -> time | None:
    """Parse ``HH:MM`` into a time; None when absent or malformed."""
    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


def _in_dark(moment: datetime, dark_start: time | None, dark_end: time | None) -> bool:
    """True when ``moment``'s wall-clock time lies in ``[dark_start, dark_end)``."""
    if dark_start is None or dark_end is None or dark_start == dark_end:
        return False
    clock = moment.timetz().replace(tzinfo=None)
    if dark_start < dark_end:
        return dark_start <= clock < dark_end
    return clock >= dark_start or clock < dark_end


def _config_dark_defaults(config_path: Path = _DEFAULT_CONFIG) -> tuple[time | None, time | None]:
    """Derive the dark window (complement of ``light_window``) from the farm config.

    The config is parsed with a tiny line reader so this script stays stdlib-only.
    """
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return None, None
    in_window = False
    start: time | None = None
    end: time | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            in_window = stripped == "light_window:"
            continue
        if not in_window:
            continue
        match = re.match(r"(start|end):\s*[\"']?([0-9]{2}:[0-9]{2})", stripped)
        if match:
            clock = _parse_clock(match.group(2))
            if match.group(1) == "start":
                start = clock
            else:
                end = clock
    if start is None or end is None:
        return None, None
    return end, start


def _fmt_dt(moment: datetime | None) -> str:
    """Format an aware datetime as a compact ISO-8601 UTC string."""
    return "" if moment is None else moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _duplicate_count(rows: Sequence[dict[str, str]]) -> int:
    """Count rows beyond the first occurrence of each non-empty sha256."""
    counts = Counter((row.get("sha256") or "").strip() for row in rows)
    counts.pop("", None)
    return sum(count - 1 for count in counts.values() if count > 1)


def _audit_zone(
    zone: str,
    rows: Sequence[dict[str, str]],
    cadence_min: int,
    dark_start: time | None,
    dark_end: time | None,
    max_missing: int,
    max_gap_min: float,
) -> dict[str, object]:
    """Audit one zone's rows against the expected cadence grid."""
    duplicates = _duplicate_count(rows)
    quality_bad = sum(1 for row in rows if (row.get("quality_flag") or "ok") != "ok")
    scale_false = sum(
        1 for row in rows if (row.get("scale_ok") or "").strip().lower() in {"false", "0", "no"}
    )
    settings_unknown = sum(
        1
        for row in rows
        if (row.get("settings_source") or "").strip().lower() not in {"exif", "app", "manual"}
    )

    dated: list[tuple[datetime, dict[str, str]]] = []
    undated = 0
    for row in rows:
        moment = _parse_timestamp(row.get("captured_at"))
        if moment is None:
            undated += 1
        else:
            dated.append((moment, row))

    result: dict[str, object] = {
        "zone": zone,
        "rows": len(rows),
        "expected_slots": 0,
        "present": 0,
        "missing": 0,
        "outside_dark_policy": 0,
        "undated": undated,
        "duplicates": duplicates,
        "duplicate_timestamps": len(dated) - len({moment for moment, _row in dated}),
        "longest_gap_minutes": 0.0,
        "longest_gap_start": "",
        "longest_gap_end": "",
        "quality_bad": quality_bad,
        "scale_false": scale_false,
        "settings_unknown": settings_unknown,
        "status": "insufficient data",
    }
    if len(rows) < 2:
        return result
    if not dated:
        result["status"] = "OK"
        return result

    first = min(moment for moment, _row in dated)
    last = max(moment for moment, _row in dated)
    step = timedelta(minutes=cadence_min)
    slot_minutes = cadence_min * 60

    def _slot_index(moment: datetime) -> int:
        return int(((moment - first).total_seconds() + 1e-9) // slot_minutes)

    expected_slots = _slot_index(last) + 1
    present_indices = {_slot_index(moment) for moment, _row in dated}
    present_indices = {index for index in present_indices if 0 <= index < expected_slots}

    missing = outside = 0
    for index in range(expected_slots):
        if index in present_indices:
            continue
        slot_start = first + step * index
        if _in_dark(slot_start, dark_start, dark_end):
            outside += 1
        else:
            missing += 1

    longest = 0.0
    longest_start = longest_end = None
    present_slots = [first + step * index for index in sorted(present_indices)]
    for gap_start, gap_end in zip(present_slots, present_slots[1:]):
        gap = (gap_end - gap_start).total_seconds() / 60.0
        if gap > longest:
            longest = gap
            longest_start, longest_end = gap_start, gap_end

    result.update(
        expected_slots=expected_slots,
        present=len(present_indices),
        missing=missing,
        outside_dark_policy=outside,
        longest_gap_minutes=longest,
        longest_gap_start=_fmt_dt(longest_start),
        longest_gap_end=_fmt_dt(longest_end),
        status="FAIL" if missing > max_missing or longest > max_gap_min else "OK",
    )
    return result


def audit_rows(
    rows: Sequence[dict[str, str]],
    cadence_min: int,
    dark_start: time | None,
    dark_end: time | None,
    max_missing: int,
    max_gap_min: float,
) -> dict[str, object]:
    """Group rows by zone and audit each group.

    Returns:
        Report dict with the resolved parameters, per-zone results and an
        overall status (``FAIL`` when any zone exceeded a threshold).
    """
    zones: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        zones.setdefault((row.get("zone_id") or "unknown").strip() or "unknown", []).append(row)
    results = [
        _audit_zone(zone, zone_rows, cadence_min, dark_start, dark_end, max_missing, max_gap_min)
        for zone, zone_rows in sorted(zones.items())
    ]
    return {
        "cadence_min": cadence_min,
        "dark_start": "" if dark_start is None else dark_start.strftime("%H:%M"),
        "dark_end": "" if dark_end is None else dark_end.strftime("%H:%M"),
        "max_missing": max_missing,
        "max_gap_min": max_gap_min,
        "rows": len(rows),
        "zones": results,
        "status": "FAIL" if any(zone["status"] == "FAIL" for zone in results) else "OK",
    }


def render_markdown(report: dict[str, object], csv_path: Path) -> str:
    """Render the audit report as Markdown."""
    zones = report["zones"]
    assert isinstance(zones, list)
    lines = [
        "# Coverage audit",
        "",
        f"- CSV: `{csv_path}`",
        f"- Cadence: {report['cadence_min']} min",
        f"- Dark window: {report['dark_start'] or 'disabled'}-{report['dark_end'] or 'disabled'}",
        f"- Thresholds: missing > {report['max_missing']}, longest gap > {report['max_gap_min']} min",
        f"- Overall: **{report['status']}**",
        "",
    ]
    if not zones:
        lines.append("no rows")
        return "\n".join(lines) + "\n"
    lines.extend([_HEADER, _SEPARATOR])
    for zone in zones:
        if zone["status"] == "insufficient data":
            lines.append(
                f"| {zone['zone']} | {zone['rows']} | - | - | - | - | {zone['undated']} | "
                f"{zone['duplicates']} | - | - | - | {zone['quality_bad']} | "
                f"{zone['scale_false']} | {zone['settings_unknown']} | insufficient data |"
            )
            continue
        lines.append(
            f"| {zone['zone']} | {zone['rows']} | {zone['expected_slots']} | "
            f"{zone['present']} | {zone['missing']} | {zone['outside_dark_policy']} | "
            f"{zone['undated']} | {zone['duplicates']} | "
            f"{zone['longest_gap_minutes']:.0f} | {zone['longest_gap_start'] or '-'} | "
            f"{zone['longest_gap_end'] or '-'} | {zone['quality_bad']} | "
            f"{zone['scale_false']} | {zone['settings_unknown']} | {zone['status']} |"
        )
    if any(zone["status"] == "insufficient data" for zone in zones):
        lines.extend(["", "insufficient data: fewer than 2 rows for at least one zone"])
    return "\n".join(lines) + "\n"


def _write_report(path: Path, text: str) -> None:
    """Write a report, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the coverage audit; returns 0 ok, 2 threshold exceeded, 1 error."""
    args = parse_args(argv)
    if args.cadence_min <= 0 or args.max_missing < 0 or args.max_gap_min < 0:
        print("audit_coverage: cadence must be > 0 and thresholds >= 0", file=sys.stderr)
        return 1
    if (args.dark_start is None) != (args.dark_end is None):
        print("audit_coverage: --dark-start and --dark-end must be given together",
              file=sys.stderr)
        return 1
    if args.dark_start is None:
        dark_start, dark_end = _config_dark_defaults()
    else:
        dark_start = _parse_clock(args.dark_start)
        dark_end = _parse_clock(args.dark_end)
        if dark_start is None or dark_end is None:
            print("audit_coverage: --dark-start/--dark-end must be HH:MM", file=sys.stderr)
            return 1
    csv_path = Path(args.csv)
    try:
        with csv_path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        report = audit_rows(
            rows, args.cadence_min, dark_start, dark_end, args.max_missing, args.max_gap_min
        )
        _write_report(Path(args.out), render_markdown(report, csv_path))
        if args.json is not None:
            json_path = Path(args.json) if args.json else Path(args.out).with_suffix(".json")
            _write_report(json_path, json.dumps(report, indent=2) + "\n")
    except (OSError, csv.Error, ValueError) as exc:
        print(f"audit_coverage: {exc}", file=sys.stderr)
        return 1
    return 2 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
