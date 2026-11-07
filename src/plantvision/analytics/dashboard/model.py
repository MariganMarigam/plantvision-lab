"""Pure data transforms for the v2 dashboard payload.

Every function here reads already-parsed CSV string rows and returns plain
dicts/lists that the template layer can serialise. No file scanning order, no
wall clock and no crop literals: ``now`` is injected and all iteration order is
explicitly sorted or follows config order.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Sequence

from plantvision.analytics.rules import (
    Finding,
    RuleConfig,
    evaluate_rules,
    is_true,
    parse_timestamp,
    quality_flags,
)
from plantvision.analytics.timeseries import TIMESERIES_COLUMNS

from .contract import FILTERS, RENDER, crops_payload
from .legacy import load_rows

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .build import Panel

_UTC = timezone.utc
_DAY_SECONDS = 86400.0

SERIES_SPEC: dict[str, tuple[str, int]] = {
    "area_px": ("px", 0),
    "area_cm2": ("cm²", 2),
    "roi_fraction_pct": ("%", 1),
    "solidity": ("ratio", 3),
    "extent": ("ratio", 3),
    "hull_area_px": ("px", 0),
    "perimeter_cm": ("cm", 2),
    "ellipse_major_px": ("px", 1),
    "ellipse_minor_px": ("px", 1),
}


@dataclass(frozen=True)
class Series:
    """One downsampled metric series with gap and missing bookkeeping."""

    unit: str
    decimals: int
    measured: int
    missing: int
    source_points: int
    runs: tuple[tuple[tuple[int, float], ...], ...]
    gaps: tuple[tuple[int, int], ...]
    stats: dict[str, float] | None
    downsampled: bool

    def as_json(self) -> dict[str, object]:
        """Return the JSON-safe representation used by the page payload."""
        return {
            "unit": self.unit,
            "decimals": self.decimals,
            "measured": self.measured,
            "missing": self.missing,
            "source_points": self.source_points,
            "downsampled": self.downsampled,
            "runs": [
                [[timestamp, round(value, 6)] for timestamp, value in run]
                for run in self.runs
            ],
            "gaps": [[start, end] for start, end in self.gaps],
            "stats": self.stats,
        }


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
    return value if math.isfinite(value) else None


def split_runs(
    points: Sequence[tuple[datetime, float]], *, min_gap_hours: float = 2.0
) -> list[list[tuple[datetime, float]]]:
    """Split a chronological series where a hole is a real capture gap.

    The implementation mirrors the frozen v1 renderer: a break is inserted when
    ``dt - prev_dt`` exceeds ``max(3 * median_gap, min_gap_hours h)``.

    Args:
        points: Chronologically sorted ``(timestamp, value)`` pairs.
        min_gap_hours: Floor for the break threshold in hours.

    Returns:
        One list per continuous run; an empty input yields an empty list.
    """
    if not points:
        return []
    if len(points) < 2:
        return [list(points)]
    gaps = [
        (current[0] - previous[0]).total_seconds()
        for previous, current in zip(points, points[1:])
    ]
    threshold = max(3.0 * statistics.median(gaps), min_gap_hours * 3600.0)
    runs: list[list[tuple[datetime, float]]] = [[points[0]]]
    for previous, current in zip(points, points[1:]):
        if (current[0] - previous[0]).total_seconds() > threshold:
            runs.append([current])
        else:
            runs[-1].append(current)
    return runs


def stats(values: Sequence[float]) -> dict[str, float] | None:
    """Descriptive statistics over finite values.

    Args:
        values: Numeric values (already filtered).

    Returns:
        A dict with ``n,min,max,median,mean,first,last`` or ``None`` when empty.
    """
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        return None
    return {
        "n": float(len(clean)),
        "min": min(clean),
        "max": max(clean),
        "median": float(statistics.median(clean)),
        "mean": float(statistics.mean(clean)),
        "first": clean[0],
        "last": clean[-1],
    }


def downsample(run: Sequence[tuple[int, float]], keep: int) -> list[tuple[int, float]]:
    """Thin one run while preserving bucket extrema and both endpoints.

    Args:
        run: ``(epoch_ms, value)`` points in x order.
        keep: Target number of points.

    Returns:
        The thinned run (still in x order).

    Raises:
        ValueError: If ``keep < 2`` (use the two endpoints explicitly instead).
    """
    if keep < 2:
        raise ValueError(f"keep must be at least 2, got {keep}")
    length = len(run)
    if length <= keep:
        return list(run)
    order: set[int] = set()
    for bucket in range(keep):
        lo = bucket * length // keep
        hi = (bucket + 1) * length // keep
        if hi <= lo:
            continue
        segment = run[lo:hi]
        minimum = min(range(len(segment)), key=lambda index: segment[index][1])
        maximum = max(range(len(segment)), key=lambda index: segment[index][1])
        order.update((lo, hi - 1, lo + minimum, lo + maximum))
    while len(order) > keep:
        protected = {
            0,
            length - 1,
            min(range(length), key=lambda index: run[index][1]),
            max(range(length), key=lambda index: run[index][1]),
        }
        middle = [index for index in sorted(order)[1:-1] if index not in protected]
        if not middle:
            break
        order.discard(middle[len(middle) // 2])
    return [run[index] for index in sorted(order)]


def _allocate(lengths: Sequence[int], budget: int) -> list[int]:
    """Allocate a point budget per run, minimum two per run."""
    if not lengths:
        return []
    total = sum(lengths)
    allocation = [
        max(2, min(length, round(budget * length / total))) for length in lengths
    ]
    while sum(allocation) > budget:
        index = max(range(len(allocation)), key=lambda i: allocation[i])
        if allocation[index] <= 2:
            break
        allocation[index] -= 1
    return allocation


def build_series(
    rows: Sequence[dict[str, str]],
    key: str,
    *,
    unit: str,
    decimals: int,
    budget: int = 240,
) -> Series:
    """Build one metric series from CSV rows.

    Args:
        rows: Parsed CSV rows.
        key: Numeric column.
        unit: Display unit.
        decimals: Display decimals.
        budget: Maximum kept points across all runs.

    Returns:
        The :class:`Series`.

    Raises:
        ValueError: If ``budget < 4``.
    """
    if budget < 4:
        raise ValueError(f"budget must be at least 4, got {budget}")
    dated: list[tuple[datetime, float]] = []
    missing = 0
    for row in rows:
        timestamp = parse_timestamp(row.get("captured_at"))
        if timestamp is None:
            continue
        value = _finite(row, key)
        if value is None:
            missing += 1
            continue
        dated.append((timestamp, value))
    dated.sort(key=lambda pair: pair[0])
    raw_runs = split_runs(dated)
    allocation = _allocate([len(run) for run in raw_runs], budget)
    kept_runs: list[tuple[tuple[int, float], ...]] = []
    for run, keep in zip(raw_runs, allocation):
        points = [
            (int(timestamp.timestamp() * 1000.0), value) for timestamp, value in run
        ]
        kept_runs.append(tuple(downsample(points, keep)))
    gaps = tuple(
        (previous[-1][0], current[0][0])
        for previous, current in zip(kept_runs, kept_runs[1:])
    )
    kept_total = sum(len(run) for run in kept_runs)
    return Series(
        unit=unit,
        decimals=decimals,
        measured=len(dated),
        missing=missing,
        source_points=len(dated) + missing,
        runs=tuple(kept_runs),
        gaps=gaps,
        stats=stats([value for _timestamp, value in dated]),
        downsampled=kept_total < len(dated),
    )


def _measured_pairs(
    rows: Sequence[dict[str, str]], key: str
) -> list[tuple[datetime, float]]:
    """Dated, finite ``(timestamp, value)`` pairs sorted ascending."""
    measured: list[tuple[datetime, float]] = []
    for row in rows:
        timestamp = parse_timestamp(row.get("captured_at"))
        if timestamp is None:
            continue
        value = _finite(row, key)
        if value is None:
            continue
        measured.append((timestamp, value))
    measured.sort(key=lambda pair: pair[0])
    return measured


def _iso_z(moment: datetime) -> str:
    """ISO-8601 UTC string with the trailing ``Z`` the page uses."""
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def points_table(
    rows: Sequence[dict[str, str]],
    keys: Sequence[str] = ("area_px", "area_cm2"),
) -> dict[str, list[int | float | None]]:
    """Columnar frame table: one shared timestamp list and one list per key.

    Rows without a parseable ``captured_at`` are dropped. Blank or non-finite
    cells become ``None`` (never ``0``). Values are rounded to 6 decimals.
    """
    out: dict[str, list[int | float | None]] = {
        "ts": [],
        **{key: [] for key in keys},
    }
    for row in rows:
        timestamp = parse_timestamp(row.get("captured_at"))
        if timestamp is None:
            continue
        out["ts"].append(int(timestamp.timestamp() * 1000.0))
        for key in keys:
            value = _finite(row, key)
            out[key].append(None if value is None else round(value, 6))
    return out


def last_frame_block(
    rows: Sequence[dict[str, str]], key: str = "area_px"
) -> dict[str, object]:
    """Last measured value, previous measured value, delta in value and percent."""
    measured = _measured_pairs(rows, key)
    if not measured:
        return {
            "at": "",
            "value": None,
            "prev": None,
            "delta": None,
            "delta_pct": None,
        }
    timestamp, last = measured[-1]
    value = round(last, 6)
    if len(measured) == 1:
        return {
            "at": _iso_z(timestamp),
            "value": value,
            "prev": None,
            "delta": None,
            "delta_pct": None,
        }
    previous = round(measured[-2][1], 6)
    delta = round(value - previous, 6)
    delta_pct = round(100.0 * delta / previous, 4) if previous != 0 else None
    return {
        "at": _iso_z(timestamp),
        "value": value,
        "prev": previous,
        "delta": delta,
        "delta_pct": delta_pct,
    }


def trailing_index_series(
    rows: Sequence[dict[str, str]], *, key: str = "area_px", count: int = 24
) -> list[list[float]]:
    """Index (first kept frame = 100) over the trailing ``count`` measured frames."""
    measured = _measured_pairs(rows, key)
    if count <= 0 or not measured:
        return []
    tail = measured[-count:]
    base = tail[0][1]
    if base <= 0:
        return []
    return [
        [int(timestamp.timestamp() * 1000.0), round(100.0 * value / base, 4)]
        for timestamp, value in tail
    ]


def _dated_rows(rows: Sequence[dict[str, str]]) -> list[tuple[datetime, dict[str, str]]]:
    """Rows with a parseable timestamp, sorted ascending."""
    dated = [
        (timestamp, row)
        for row in rows
        if (timestamp := parse_timestamp(row.get("captured_at"))) is not None
    ]
    dated.sort(key=lambda pair: pair[0])
    return dated


def _quartiles(values: Sequence[float]) -> tuple[float | None, float | None]:
    """Inclusive quartiles; a single value yields the value for both."""
    if not values:
        return None, None
    if len(values) == 1:
        return values[0], values[0]
    q1, _q2, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return q1, q3


def panel_kpi(
    rows: Sequence[dict[str, str]], *, now: datetime
) -> dict[str, float | None]:
    """Headline percentages, never inventing a value for an unmeasured column.

    Args:
        rows: Parsed CSV rows.
        now: Reference time for freshness.

    Returns:
        ``scale_pct, quality_pct, shape_pct, freshness_pct`` (any may be None).
    """
    total = len(rows)
    scale_pct = (
        100.0 * sum(1 for row in rows if is_true(row.get("scale_ok"))) / total
        if total
        else None
    )
    quality_measured = any(_cell(row, "quality_flag") for row in rows)
    quality_pct = (
        100.0
        * sum(1 for row in rows if quality_flags(row.get("quality_flag")))
        / total
        if quality_measured and total
        else None
    )
    shape_rows = sum(
        1
        for row in rows
        if _cell(row, "solidity") or _cell(row, "extent")
    )
    shape_pct = 100.0 * shape_rows / total if shape_rows and total else None
    dated = _dated_rows(rows)
    freshness_pct: float | None = None
    if dated:
        age_days = max(0.0, (now - dated[-1][0]).total_seconds() / _DAY_SECONDS)
        freshness_pct = 100.0 * max(0.0, min(1.0, 1.0 - age_days / 7.0))
    return {
        "scale_pct": None if scale_pct is None else round(scale_pct, 2),
        "quality_pct": None if quality_pct is None else round(quality_pct, 2),
        "shape_pct": None if shape_pct is None else round(shape_pct, 2),
        "freshness_pct": None if freshness_pct is None else round(freshness_pct, 2),
    }


def daily_buckets(rows: Sequence[dict[str, str]]) -> list[dict[str, object]]:
    """Aggregate rows into UTC calendar days.

    Args:
        rows: Parsed CSV rows.

    Returns:
        One dict per day, sorted by date.
    """
    groups: dict[str, list[dict[str, str]]] = {}
    for timestamp, row in _dated_rows(rows):
        groups.setdefault(timestamp.date().isoformat(), []).append(row)
    buckets: list[dict[str, object]] = []
    for day in sorted(groups):
        day_rows = groups[day]
        area = [
            value
            for row in day_rows
            if (value := _finite(row, "area_px")) is not None
        ]
        area_cm2 = [
            value
            for row in day_rows
            if is_true(row.get("scale_ok"))
            and (value := _finite(row, "area_cm2")) is not None
        ]
        q1, q3 = _quartiles(area)
        scale_ok = sum(1 for row in day_rows if is_true(row.get("scale_ok")))
        buckets.append(
            {
                "date": day,
                "frames": len(day_rows),
                "measured_area_px": len(area),
                "median_area_px": float(statistics.median(area)) if area else None,
                "median_area_cm2": (
                    None
                    if not area_cm2
                    else round(float(statistics.median(area_cm2)), 3)
                ),
                "min_area_px": min(area) if area else None,
                "max_area_px": max(area) if area else None,
                "scale_pct": round(100.0 * scale_ok / len(day_rows), 2),
                "q1_area_px": q1,
                "q3_area_px": q3,
            }
        )
    return buckets


def quality_block(rows: Sequence[dict[str, str]]) -> dict[str, object]:
    """Physical quality-defect token counts.

    Args:
        rows: Parsed CSV rows.

    Returns:
        ``measured`` plus a ``tokens`` count map and ``rate_pct``.
    """
    cells = [_cell(row, "quality_flag") for row in rows]
    measured_rows = [cell for cell in cells if cell]
    tokens: dict[str, int] = {"ok": 0, "blur": 0, "dark": 0, "bright": 0}
    defects = 0
    for cell in measured_rows:
        flags = quality_flags(cell)
        if flags:
            defects += 1
            for token in flags:
                tokens[token] = tokens.get(token, 0) + 1
        else:
            tokens["ok"] += 1
    measured = bool(measured_rows)
    rate = round(100.0 * defects / len(measured_rows), 2) if measured else None
    return {
        "measured": measured,
        "tokens": {key: tokens[key] for key in sorted(tokens)},
        "rate_pct": rate,
    }


def provenance_block(rows: Sequence[dict[str, str]]) -> dict[str, object]:
    """Camera-settings provenance coverage and distinct settings.

    Args:
        rows: Parsed CSV rows.

    Returns:
        ``settings_source`` counts, ``recorded_pct`` and ``distinct_settings``.
    """
    counter = {"blank": 0, "exif": 0, "app": 0, "manual": 0, "unavailable": 0}
    settings: set[tuple[str, str, str]] = set()
    for row in rows:
        source = _cell(row, "settings_source").lower()
        if source in counter:
            counter[source] += 1
        else:
            counter["blank"] += 1
        triple = (
            _cell(row, "exposure_s"),
            _cell(row, "white_balance"),
            _cell(row, "gain_db"),
        )
        if any(triple):
            settings.add(triple)
    recorded = counter["exif"] + counter["app"] + counter["manual"]
    return {
        "settings_source": counter,
        "recorded_pct": round(100.0 * recorded / len(rows), 2) if rows else None,
        "distinct_settings": [list(item) for item in sorted(settings)[:8]],
    }


def gaps_block(rows: Sequence[dict[str, str]]) -> dict[str, object]:
    """Capture intervals over 12 hours.

    Args:
        rows: Parsed CSV rows.

    Returns:
        ``count, max_hours, over_12h, over_24h, items``.
    """
    dated = _dated_rows(rows)
    diffs = [
        (previous[0], current[0], (current[0] - previous[0]).total_seconds() / 3600.0)
        for previous, current in zip(dated, dated[1:])
    ]
    items = [
        {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "hours": round(hours, 2),
        }
        for start, end, hours in sorted(diffs, key=lambda item: item[2], reverse=True)
        if hours > 12.0
    ][:10]
    return {
        "count": len(diffs),
        "max_hours": round(max((item[2] for item in diffs), default=0.0), 2) if diffs else None,
        "over_12h": sum(1 for item in diffs if item[2] > 12.0),
        "over_24h": sum(1 for item in diffs if item[2] > 24.0),
        "items": items,
    }


def coverage_block(rows: Sequence[dict[str, str]]) -> list[dict[str, object]]:
    """Non-blank cell counts per canonical column.

    Args:
        rows: Parsed CSV rows.

    Returns:
        One dict per ``TIMESERIES_COLUMNS`` entry, in schema order.
    """
    total = len(rows)
    result: list[dict[str, object]] = []
    for column in TIMESERIES_COLUMNS:
        measured = sum(1 for row in rows if _cell(row, column))
        result.append(
            {
                "column": column,
                "measured": measured,
                "total": total,
                "pct": round(100.0 * measured / total, 1) if total else 0.0,
            }
        )
    return result


_SHAPE_AXES: tuple[str, ...] = (
    "solidity",
    "extent",
    "area_to_hull",
    "perimeter_to_bbox",
    "ellipse_ratio",
)


def _shape_values(row: dict[str, str]) -> dict[str, float]:
    """Raw (not normalised) shape values present in one row."""
    values: dict[str, float] = {}
    for key in ("solidity", "extent"):
        value = _finite(row, key)
        if value is not None:
            values[key] = value
    area = _finite(row, "area_px")
    hull = _finite(row, "hull_area_px")
    if area is not None and hull is not None and hull > 0:
        values["area_to_hull"] = area / hull
    perimeter = _finite(row, "perimeter_px")
    bbox_w = _finite(row, "bbox_w")
    bbox_h = _finite(row, "bbox_h")
    if perimeter is not None and bbox_w and bbox_h and (bbox_w + bbox_h) > 0:
        values["perimeter_to_bbox"] = perimeter / (2.0 * (bbox_w + bbox_h))
    minor = _finite(row, "ellipse_minor_px")
    major = _finite(row, "ellipse_major_px")
    if minor is not None and major is not None and major > 0:
        values["ellipse_ratio"] = minor / major
    return values


def normalise_shape(rows: Sequence[dict[str, str]]) -> list[dict[str, float]]:
    """Min-max normalise the five shape axes within a panel.

    Args:
        rows: Parsed CSV rows.

    Returns:
        One dict per row containing only the axes the row measured, each in
        ``0..1`` (``0.5`` when the axis has no spread).
    """
    raw = [_shape_values(row) for row in rows]
    ranges: dict[str, tuple[float, float]] = {}
    for axis in _SHAPE_AXES:
        values = [row[axis] for row in raw if axis in row]
        if values:
            ranges[axis] = (min(values), max(values))
    normalised: list[dict[str, float]] = []
    for row in raw:
        result: dict[str, float] = {}
        for axis, value in row.items():
            lo, hi = ranges[axis]
            result[axis] = 0.5 if hi == lo else (value - lo) / (hi - lo)
        normalised.append(result)
    return normalised


def _load_panel_rows(dataset: "Panel") -> list[dict[str, str]]:
    """Load a panel CSV through the frozen v1 loader (header validation)."""
    rows = load_rows(dataset.csv_path)
    where = getattr(dataset, "where", None) or {}
    if not where:
        return rows
    return [
        row
        for row in rows
        if all((row.get(key) or "").strip() == value for key, value in where.items())
    ]


def panel_payload(
    panel: "Panel",
    rows: Sequence[dict[str, str]],
    *,
    now: datetime,
    config: RuleConfig | None = None,
) -> dict[str, object]:
    """Assemble the full per-panel payload block.

    Args:
        panel: Panel metadata from the config.
        rows: Parsed CSV rows.
        now: Reference time.
        config: Optional rule thresholds.

    Returns:
        The JSON-ready panel dict.
    """
    findings = evaluate_rules(rows, now=now, config=config)
    dated = _dated_rows(rows)
    dates = sorted({timestamp.date().isoformat() for timestamp, _row in dated})
    first_at = dated[0][0].isoformat() if dated else ""
    last_at = dated[-1][0].isoformat() if dated else ""
    span_hours = (
        (dated[-1][0] - dated[0][0]).total_seconds() / 3600.0 if dated else None
    )
    age_days = (
        max(0.0, (now - dated[-1][0]).total_seconds() / _DAY_SECONDS) if dated else None
    )
    severities = {finding.severity for finding in findings}
    if "critical" in severities:
        verdict = "critical"
    elif "warn" in severities:
        verdict = "warn"
    elif findings:
        verdict = "ok"
    else:
        verdict = "ok" if rows else "unknown"
    camera = next((_cell(row, "camera_id") for row in rows if _cell(row, "camera_id")), "")
    zone = next((_cell(row, "zone_id") for row in rows if _cell(row, "zone_id")), "")
    scale_missing = [
        int(timestamp.timestamp() * 1000.0)
        for timestamp, row in dated
        if not is_true(row.get("scale_ok")) or not _cell(row, "area_cm2")
    ]
    radar_rows = [row for row in normalise_shape(rows) if row]
    radar: list[dict[str, object]] = []
    for axis in _SHAPE_AXES:
        values = [row[axis] for row in radar_rows if axis in row]
        if values:
            radar.append({"axis": axis, "value": round(float(statistics.fmean(values)), 4)})
    raw_axes = [_shape_values(row) for row in rows]
    ranges: dict[str, list[float]] = {}
    for axis in _SHAPE_AXES:
        values = [row[axis] for row in raw_axes if axis in row]
        if values:
            ranges[axis] = [min(values), max(values)]
    return {
        "id": panel.id,
        "label": panel.label,
        "crop": panel.crop,
        "method": panel.method,
        "method_label": panel.method_label,
        "pipeline_version": panel.pipeline_version,
        "source": str(panel.csv_path),
        "note": panel.note,
        "camera": camera,
        "zone": zone,
        "rows": len(rows),
        "days": len(dates),
        "first_at": first_at,
        "last_at": last_at,
        "span_hours": None if span_hours is None else round(span_hours, 2),
        "age_days": None if age_days is None else round(age_days, 2),
        "verdict": verdict,
        "kpi": panel_kpi(rows, now=now),
        "coverage": coverage_block(rows),
        "series": {
            key: build_series(rows, key, unit=unit, decimals=decimals).as_json()
            for key, (unit, decimals) in SERIES_SPEC.items()
        },
        "daily": daily_buckets(rows),
        "quality": quality_block(rows),
        "provenance": provenance_block(rows),
        "gaps": gaps_block(rows),
        "shape": {"radar": radar, "range": ranges},
        "scale_missing": scale_missing,
        "points": points_table(rows),
        "last_frame": last_frame_block(rows),
        "last_change": trailing_index_series(rows),
        "frames": [],
        "alerts": {
            "critical": sum(1 for finding in findings if finding.severity == "critical"),
            "warn": sum(1 for finding in findings if finding.severity == "warn"),
        },
    }


def _thin_points(
    points: Sequence[tuple[float, float]], budget: int = 240
) -> list[list[float]]:
    """Apply the panel series budget to a comparison curve."""
    if len(points) <= budget:
        return [[round(x, 4), round(y, 4)] for x, y in points]
    pseudo = [(index, value) for index, (_x, value) in enumerate(points)]
    keep = downsample(pseudo, budget)
    indices = {index for index, _value in keep}
    result: list[list[float]] = []
    for index in sorted(indices):
        x, y = points[index]
        result.append([round(x, 4), round(y, 4)])
    return result


def comparison_payload(panels: Sequence[dict[str, object]]) -> dict[str, object]:
    """Index each panel's full area series to 100 at its first measured frame.

    Args:
        panels: Panel payloads.

    Returns:
        ``{"series": [...], "excluded": [...], "max_hours": float|None}``.
    """
    series: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    max_hours: float | None = None
    for panel in panels:
        panel_series = panel.get("series", {})
        area = panel_series.get("area_px", {}) if isinstance(panel_series, dict) else {}
        runs = area.get("runs", []) if isinstance(area, dict) else []
        points = [
            (timestamp, value)
            for run in runs
            for timestamp, value in run
        ]
        base = points[0][1] if points else None
        if len(points) < 2 or base is None or base <= 0:
            excluded.append(
                {"id": panel["id"], "label": panel["label"], "state": "insufficient"}
            )
            continue
        first = points[0][0]
        relative = [
            ((timestamp - first) / 3_600_000.0, value / base * 100.0)
            for timestamp, value in points
        ]
        hours = relative[-1][0]
        max_hours = hours if max_hours is None else max(max_hours, hours)
        series.append(
            {
                "id": panel["id"],
                "label": panel["label"],
                "method": panel["method"],
                "points": _thin_points(relative),
            }
        )
    return {"series": series, "excluded": excluded, "max_hours": max_hours}


def _calendar_days(start: date, end: date) -> list[str]:
    """Every ISO date from ``start`` to ``end`` inclusive."""
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def calendar_payload(panels: Sequence[dict[str, object]]) -> dict[str, object]:
    """Global UTC calendar grid plus per-panel frame counts.

    Args:
        panels: Panel payloads.

    Returns:
        ``start``, ``end``, ``days`` and ``rows``.
    """
    all_dates = sorted(
        bucket["date"]
        for panel in panels
        for bucket in panel.get("daily", [])
        if bucket.get("date")
    )
    if not all_dates:
        return {"start": "", "end": "", "days": 0, "rows": []}
    start = date.fromisoformat(all_dates[0])
    end = date.fromisoformat(all_dates[-1])
    days = _calendar_days(start, end)
    rows: list[dict[str, object]] = []
    carry_frames = 0
    for panel in panels:
        daily = {bucket["date"]: int(bucket["frames"]) for bucket in panel.get("daily", [])}
        cells = [{"date": day, "frames": daily.get(day, 0)} for day in days]
        panel_dates = sorted(daily)
        hollow = 0
        if panel_dates:
            span = _calendar_days(
                date.fromisoformat(panel_dates[0]), date.fromisoformat(panel_dates[-1])
            )
            hollow = sum(1 for day in span if daily.get(day, 0) <= 0)
        if any(cell["frames"] > 0 for cell in cells):
            carry_frames += 1
        rows.append({"panel": panel["id"], "cells": cells, "hollow_days": hollow})
    return {
        "start": days[0],
        "end": days[-1],
        "days": sum(
            1
            for index in range(len(days))
            if any(row["cells"][index]["frames"] > 0 for row in rows)
        ),
        "rows": rows,
    }


_ANCHORS: dict[str, str] = {
    "growth-stall": "ch-gr-rate-bars",
    "area-drop": "ch-gr-area-px",
    "solidity-drop": "ch-sh-solidity",
    "scale-coverage": "ch-dq-scale-stacked",
    "capture-gap": "ch-dq-gap-bars",
    "stale-data": "ch-ov-kpi-rings",
    "quality-flag-rate": "ch-dq-quality-bars",
    "camera-settings-change": "ch-dq-provenance-heatmap",
    "camera-settings-provenance": "ch-dq-provenance-heatmap",
}
_SEVERITY_ORDER = {"critical": 0, "warn": 1, "ok": 2}


def findings_payload(
    panels: Sequence[dict[str, object]],
    findings: Sequence[tuple[str, Finding]],
    anchors: dict[str, str],
) -> list[dict[str, object]]:
    """Flatten rule findings with their chart anchors.

    Args:
        panels: Panel payloads (for labels/zones).
        findings: ``(panel_id, Finding)`` pairs.
        anchors: Rule id to chart id map.

    Returns:
        Sorted list of JSON-ready findings.
    """
    labels = {panel["id"]: panel["label"] for panel in panels}
    items = [
        {
            "severity": finding.severity,
            "rule_id": finding.rule_id,
            "panel": panel_id,
            "panel_label": labels.get(panel_id, ""),
            "zone": finding.zone,
            "detail": finding.detail,
            "value": finding.value,
            "threshold": finding.threshold,
            "window_start": finding.window_start,
            "window_end": finding.window_end,
            "anchor": anchors.get(finding.rule_id, ""),
        }
        for panel_id, finding in findings
    ]
    items.sort(
        key=lambda item: (
            _SEVERITY_ORDER.get(str(item["severity"]), 9),
            str(item["panel"]),
            str(item["zone"]),
            str(item["rule_id"]),
        )
    )
    return items


_METHOD_STEPS: tuple[dict[str, str], ...] = (
    {"step": "capture", "module": "plantvision.capture.pull", "detail": "JPEG + sidecar arrives from the rig"},
    {"step": "scale", "module": "plantvision.vision.scale", "detail": "45 mm marker gives px_per_mm per frame"},
    {"step": "segmentation", "module": "plantvision.vision.segmentation", "detail": "marker-prompt mask or threshold segmentation"},
    {"step": "traits", "module": "plantvision.vision.traits", "detail": "area, hull, perimeter, ellipse fit"},
    {"step": "metrics", "module": "plantvision.analytics.timeseries", "detail": "one CSV row per frame, blank = not measurable"},
    {"step": "rules", "module": "plantvision.analytics.rules", "detail": "deterministic thresholds, no LLM"},
    {"step": "dashboard", "module": "plantvision.analytics.dashboard", "detail": "this static page"},
)


def method_payload(panels: Sequence[dict[str, object]]) -> dict[str, object]:
    """Static pipeline diagram data plus panel notes.

    Args:
        panels: Panel payloads.

    Returns:
        ``{"pipeline": [...], "notes": [...]}``.
    """
    notes = [str(panel["note"]) for panel in panels if panel.get("note")]
    return {"pipeline": [dict(step) for step in _METHOD_STEPS], "notes": notes}


def resolve_now(
    rows_by_panel: dict[str, Sequence[dict[str, str]]], now: datetime | None
) -> tuple[datetime, str]:
    """Resolve the reference time and say where it came from.

    Args:
        rows_by_panel: Parsed rows keyed by panel id.
        now: CLI reference time, or ``None``.

    Returns:
        ``(now_utc, "cli"|"data"|"none")``.
    """
    if now is not None:
        return (now if now.tzinfo else now.replace(tzinfo=_UTC)).astimezone(_UTC), "cli"
    latest: datetime | None = None
    for rows in rows_by_panel.values():
        for timestamp, _row in _dated_rows(rows):
            if latest is None or timestamp > latest:
                latest = timestamp
    if latest is None:
        return datetime(1970, 1, 1, tzinfo=_UTC), "none"
    return latest.astimezone(_UTC), "data"


def build_payload(
    datasets: Sequence["Panel"],
    *,
    now: datetime | None,
    title: str,
    config: RuleConfig | None = None,
) -> dict[str, object]:
    """Load every store and assemble the complete page payload.

    Args:
        datasets: Panel definitions from the config.
        now: CLI reference time, or ``None`` (data-derived).
        title: Page title (must be non-empty).
        config: Optional rule thresholds.

    Returns:
        The JSON-ready payload.

    Raises:
        ValueError: If ``title`` is empty.
    """
    if not title.strip():
        raise ValueError("title must not be empty")
    rows_by_panel = {
        panel.id: _load_panel_rows(panel) for panel in datasets
    }
    now_utc, now_source = resolve_now(rows_by_panel, now)
    panels: list[dict[str, object]] = []
    pairs: list[tuple[str, Finding]] = []
    for panel in datasets:
        rows = rows_by_panel[panel.id]
        panels.append(panel_payload(panel, rows, now=now_utc, config=config))
        pairs.extend(
            (panel.id, finding)
            for finding in evaluate_rules(rows, now=now_utc, config=config)
        )
    dated = [
        (timestamp, row)
        for rows in rows_by_panel.values()
        for timestamp, row in _dated_rows(rows)
    ]
    all_dates = sorted({timestamp.date().isoformat() for timestamp, _row in dated})
    critical = sum(1 for _panel_id, finding in pairs if finding.severity == "critical")
    warn = sum(1 for _panel_id, finding in pairs if finding.severity == "warn")
    totals = {
        "panels": len(datasets),
        "rows": sum(len(rows) for rows in rows_by_panel.values()),
        "days": len(all_dates),
        "first_at": min((timestamp for timestamp, _row in dated), default=None),
        "last_at": max((timestamp for timestamp, _row in dated), default=None),
        "critical": critical,
        "warn": warn,
    }
    totals["first_at"] = (
        totals["first_at"].isoformat() if totals["first_at"] is not None else ""
    )
    totals["last_at"] = (
        totals["last_at"].isoformat() if totals["last_at"] is not None else ""
    )
    return {
        "schema": "pv-dashboard/2",
        "title": title,
        "generated_at": _iso_z(now_utc) if now_source == "cli" else None,
        "now": _iso_z(now_utc),
        "now_source": now_source,
        "totals": totals,
        "panels": panels,
        "renderer": dict(RENDER),
        "filters": {name: list(values) for name, values in FILTERS.items()},
        "crops": crops_payload(panels),
        "comparison": comparison_payload(panels),
        "calendar": calendar_payload(panels),
        "findings": findings_payload(panels, pairs, _ANCHORS),
        "method": method_payload(panels),
        "cards": [],
        "frames": [],
    }
