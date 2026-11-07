"""Pure per-row and per-series derivations (D01–D32).

``None`` means "not computable from the inputs". A measured zero stays zero and
is never replaced by a missing sentinel.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone
from typing import Mapping, Sequence

from plantvision.analytics.dashboard.model import build_series
from plantvision.analytics.rules import is_true, parse_timestamp
from plantvision.analytics.validity import condition_key

from .types import SeriesBlock

_UTC = timezone.utc
_DAY_SECONDS = 86400.0


def finite(row: Mapping[str, str], key: str) -> float | None:
    """Read a finite float from a row cell; blank/invalid -> ``None``."""
    raw = (row.get(key) or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def condition_key_for(panel: object, row: Mapping[str, str]) -> str:
    """Compose the canonical condition key for one panel row (D01)."""
    camera = (row.get("camera_id") or "").strip()
    scale = getattr(panel, "scale_marker", "") or (
        "aruco45" if is_true(row.get("scale_ok")) else "none"
    )
    return condition_key(
        {
            "light": (row.get("light_regime") or getattr(panel, "light_regime", "") or "").strip(),
            "crop": str(getattr(panel, "crop", "") or ""),
            "rig": camera,
            "scale": scale,
            "pose": str(getattr(panel, "pose", "") or "side"),
        }
    )


def series_block(
    rows: Sequence[Mapping[str, str]],
    key: str,
    *,
    unit: str,
    decimals: int,
    budget: int = 240,
    condition: str = "",
    state: str = "ok",
    validity: Mapping[str, object] | None = None,
) -> SeriesBlock:
    """Build one gated metric series.

    Args:
        rows: Gated rows (metric cells may be blank).
        key: Numeric column.
        unit: Display unit.
        decimals: Display decimals.
        budget: Maximum kept points.
        condition: Canonical condition key.
        state: Resolved series state.
        validity: Validity envelope for the metric.

    Returns:
        The immutable series block.
    """
    series = build_series(
        [dict(row) for row in rows], key, unit=unit, decimals=decimals, budget=budget
    )
    draw = {
        "invalid": "hatch",
        "unproven": "dashed",
        "empty": "none",
        "not_recorded": "none",
        "ok": "solid",
    }.get(state, "none")
    return SeriesBlock(
        unit=series.unit,
        decimals=series.decimals,
        measured=series.measured,
        missing=series.missing,
        source_points=series.source_points,
        downsampled=series.downsampled,
        runs=series.runs,
        gaps=series.gaps,
        stats=series.stats,
        condition_key=condition,
        series_state=state,
        draw=draw,
        validity=dict(validity or {}),
    )


def stats(values: Sequence[float]) -> dict[str, float] | None:
    """Descriptive statistics over finite values (``None`` when empty)."""
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


def circularity(row: Mapping[str, str]) -> float | None:
    """``4π·area_px / perimeter_px²`` (D07); perimeter 0/blank -> ``None``."""
    area = finite(row, "area_px")
    perimeter = finite(row, "perimeter_px")
    if area is None or perimeter is None or perimeter <= 0:
        return None
    return 4.0 * math.pi * area / (perimeter * perimeter)


def rgr_pct_day(rows: Sequence[Mapping[str, str]]) -> float | None:
    """Relative growth rate on daily area medians (D03)."""
    groups: dict[str, list[float]] = {}
    for row in rows:
        timestamp = parse_timestamp(row.get("captured_at"))
        value = finite(row, "area_px")
        if timestamp is None or value is None or value <= 0:
            continue
        groups.setdefault(timestamp.date().isoformat(), []).append(value)
    if len(groups) < 2:
        return None
    days = sorted(groups)
    first_day, last_day = days[0], days[-1]
    first = statistics.median(groups[first_day])
    last = statistics.median(groups[last_day])
    elapsed = (
        datetime.fromisoformat(last_day) - datetime.fromisoformat(first_day)
    ).days
    if elapsed <= 0 or first <= 0 or last <= 0:
        return None
    return 100.0 * (math.log(last) - math.log(first)) / elapsed


def daily_index(rows: Sequence[Mapping[str, str]], key: str = "area_px") -> list[dict[str, object]]:
    """Daily medians indexed to 100 at the first measured day (D23)."""
    groups: dict[str, list[float]] = {}
    for row in rows:
        timestamp = parse_timestamp(row.get("captured_at"))
        value = finite(row, key)
        if timestamp is None or value is None:
            continue
        groups.setdefault(timestamp.date().isoformat(), []).append(value)
    if not groups:
        return []
    days = sorted(groups)
    base = statistics.median(groups[days[0]])
    if base <= 0:
        return []
    return [
        {
            "date": day,
            "median": round(float(statistics.median(groups[day])), 3),
            "index": round(100.0 * statistics.median(groups[day]) / base, 1),
            "n": len(groups[day]),
        }
        for day in days
    ]


def index_points(rows: Sequence[Mapping[str, str]]) -> list[dict[str, object]]:
    """Indexed series points anchored at the first measured frame (D19–D22)."""
    measured = [
        (parse_timestamp(row.get("captured_at")), finite(row, "area_px"))
        for row in rows
    ]
    pairs = [
        (timestamp, value)
        for timestamp, value in measured
        if timestamp is not None and value is not None
    ]
    if not pairs:
        return []
    pairs.sort(key=lambda pair: pair[0])  # type: ignore[arg-type]
    first_ts, first_value = pairs[0]  # type: ignore[misc]
    if first_value is None or first_value <= 0:
        return []
    points: list[dict[str, object]] = []
    for timestamp, value in pairs:
        points.append(
            {
                "ts": int(timestamp.timestamp() * 1000.0),  # type: ignore[union-attr]
                "hours": round(
                    (timestamp - first_ts).total_seconds() / 3600.0, 1  # type: ignore[operator]
                ),
                "index": round(100.0 * float(value) / first_value, 1),
            }
        )
    return points


def box_summary(values: Sequence[float]) -> dict[str, float] | None:
    """Five-number summary with 1.5·IQR whiskers (D29)."""
    clean = sorted(value for value in values if math.isfinite(value))
    if not clean:
        return None
    if len(clean) == 1:
        value = clean[0]
        return {"lo": value, "q1": value, "median": value, "q3": value, "hi": value}
    q1, _q2, q3 = statistics.quantiles(clean, n=4, method="inclusive")
    iqr = q3 - q1
    low = q1 - 1.5 * iqr
    high = q3 + 1.5 * iqr
    inside = [value for value in clean if low <= value <= high]
    return {
        "lo": min(inside),
        "q1": q1,
        "median": float(statistics.median(clean)),
        "q3": q3,
        "hi": max(inside),
    }


def coverage_pct(rows: Sequence[Mapping[str, str]], column: str) -> float:
    """Share of non-blank cells in one column (D30)."""
    if not rows:
        return 0.0
    return 100.0 * sum(1 for row in rows if (row.get(column) or "").strip()) / len(rows)


def gap_hours(rows: Sequence[Mapping[str, str]]) -> list[float]:
    """Consecutive capture intervals in hours (D17), sorted ascending."""
    stamps = sorted(
        timestamp
        for row in rows
        if (timestamp := parse_timestamp(row.get("captured_at"))) is not None
    )
    return [
        round((current - previous).total_seconds() / 3600.0, 2)
        for previous, current in zip(stamps, stamps[1:])
    ]
