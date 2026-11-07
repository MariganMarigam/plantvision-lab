"""Pure, deterministic rule engine over metrics-CSV rows.

The module reads already-parsed CSV string rows and returns :class:`Finding`
objects. It performs no file I/O, no plotting and never reads the wall clock:
callers inject ``now``. Thresholds live in :class:`RuleConfig`.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

SEVERITY_ORDER: dict[str, int] = {"critical": 0, "warn": 1}
VALIDITY_RULE_ID = "validity-violation"
KNOWN_RULES: frozenset[str] = frozenset(
    {
        "growth-stall",
        "area-drop",
        "solidity-drop",
        "scale-coverage",
        "capture-gap",
        "stale-data",
        "quality-flag-rate",
        "camera-settings-change",
        "camera-settings-provenance",
        VALIDITY_RULE_ID,
    }
)


@dataclass(frozen=True)
class RuleConfig:
    """First-pass thresholds for every rule (tuned later, not CLI flags)."""

    growth_window_hours: float = 24.0
    growth_stall_min_pct: float = 2.0
    area_drop_warn_pct: float = 15.0
    area_drop_critical_pct: float = 30.0
    solidity_drop_warn: float = 0.08
    solidity_drop_critical: float = 0.15
    scale_drop_warn_pt: float = 15.0
    scale_drop_critical_pt: float = 30.0
    gap_warn_hours: float = 12.0
    gap_critical_hours: float = 24.0
    stale_warn_days: float = 2.0
    stale_critical_days: float = 7.0
    quality_window_hours: float = 24.0
    quality_warn_pct: float = 10.0
    quality_critical_pct: float = 25.0
    settings_provenance_min_pct: float = 50.0
    min_frames: int = 6
    baseline_frames: int = 30
    recent_frames: int = 3
    validity_violation_invalid_severity: str = "critical"
    validity_violation_unproven_severity: str = "warn"


@dataclass(frozen=True)
class Finding:
    """One rule outcome for one zone."""

    rule_id: str
    severity: str
    zone: str
    detail: str
    value: float | None = None
    threshold: float | None = None
    window_start: str = ""
    window_end: str = ""


def parse_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp; blank, invalid or ``None`` -> ``None``.

    A trailing ``Z`` is normalised to ``+00:00``; naive results are treated as
    UTC.

    Args:
        value: Raw CSV cell.

    Returns:
        A timezone-aware datetime, or ``None`` when unparseable.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _fmt_ts(value: datetime | str | None) -> str:
    """Format a timestamp as ``27 Oct 15:48 UTC``.

    Args:
        value: A ``datetime`` (naive treated as UTC), an ISO-8601 string, or
            ``None``.

    Returns:
        The UTC ``day month hour:minute`` form; an empty string when the value
        is missing or unparseable.
    """
    if value is None:
        return ""
    parsed = parse_timestamp(value) if isinstance(value, str) else value
    if parsed is None:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%d %b %H:%M UTC")


def is_true(value: str | None) -> bool:
    """Return whether a CSV boolean cell represents true."""
    if value is None:
        return False
    return value.strip().lower() in {"true", "1", "yes"}


def quality_flags(value: str | None) -> tuple[str, ...]:
    """Split a ``quality_flag`` cell into non-empty tokens other than ``ok``."""
    if value is None:
        return ()
    flags: list[str] = []
    for token in value.split("|"):
        stripped = token.strip()
        if stripped and stripped.lower() != "ok":
            flags.append(stripped)
    return tuple(flags)


def _num(row: dict[str, str], key: str) -> float | None:
    """Read a finite float from a row cell; blank/non-numeric/inf -> ``None``."""
    raw = row.get(key)
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def _dated(rows: Sequence[dict[str, str]]) -> list[tuple[datetime, dict[str, str]]]:
    """Pair rows with parsed timestamps, sorted chronologically (stable)."""
    dated: list[tuple[datetime, dict[str, str]]] = []
    for row in rows:
        ts = parse_timestamp(row.get("captured_at"))
        if ts is not None:
            dated.append((ts, row))
    dated.sort(key=lambda pair: pair[0])
    return dated


def _zones(rows: Sequence[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Group rows by trimmed ``zone_id``; blank becomes ``"unknown"``."""
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        zone = (row.get("zone_id") or "").strip() or "unknown"
        groups.setdefault(zone, []).append(row)
    return groups


def _true_share(rows: Sequence[dict[str, str]]) -> float:
    """Percentage of rows whose ``scale_ok`` cell is true (0.0 for no rows)."""
    if not rows:
        return 0.0
    return 100.0 * sum(1 for row in rows if is_true(row.get("scale_ok"))) / len(rows)


def _recent_baseline(
    values: Sequence[float], recent: int, baseline: int
) -> tuple[list[float], list[float]] | None:
    """Split chronological values into (baseline, recent) slices.

    Returns ``None`` when there are fewer than ``recent + 3`` values.
    """
    if len(values) < recent + 3:
        return None
    recent_values = list(values[-recent:])
    base_values = list(values[max(0, len(values) - recent - baseline): len(values) - recent])
    return base_values, recent_values


def _finding(
    rule_id: str,
    severity: str,
    zone: str,
    detail: str,
    *,
    value: float | None = None,
    threshold: float | None = None,
    window_start: str = "",
    window_end: str = "",
) -> Finding:
    """Construct a :class:`Finding` with keyword-only optional fields."""
    return Finding(
        rule_id=rule_id,
        severity=severity,
        zone=zone,
        detail=detail,
        value=value,
        threshold=threshold,
        window_start=window_start,
        window_end=window_end,
    )


def _zone_findings(
    zone: str, zone_rows: Sequence[dict[str, str]], now: datetime, cfg: RuleConfig
) -> list[Finding]:
    """Evaluate every rule for one zone."""
    findings: list[Finding] = []
    dated = _dated(zone_rows)
    last_age_days: float | None = None
    if dated:
        last_age_days = max(0.0, (now - dated[-1][0]).total_seconds() / 86400)

    # 6. growth-stall
    if dated:
        last = dated[-1][0]
        stale_note = (
            f" (as of {_fmt_ts(last)})"
            if last_age_days is not None
            and last_age_days * 24 > cfg.growth_window_hours
            else ""
        )
        window = [
            row for ts, row in dated
            if ts >= last - timedelta(hours=cfg.growth_window_hours)
        ]
        if len(window) >= cfg.min_frames:
            values = [value for row in window if (value := _num(row, "area_px")) is not None]
            mid = len(values) // 2
            if mid >= 2:
                first_median = statistics.median(values[:mid])
                if first_median > 0:
                    pct = (
                        statistics.median(values[mid:]) - first_median
                    ) / first_median * 100
                    if abs(pct) < cfg.growth_stall_min_pct:
                        findings.append(_finding(
                            "growth-stall", "warn", zone,
                            f"area_px moved {pct:+.1f}% over the last "
                            f"{cfg.growth_window_hours:g} h ({len(window)} frames) · "
                            f"below the {cfg.growth_stall_min_pct:g}% change floor"
                            f"{stale_note}",
                            value=pct, threshold=cfg.growth_stall_min_pct,
                        ))

    # 7a. area-drop
    area_values = [
        value for _ts, row in dated if (value := _num(row, "area_px")) is not None
    ]
    slices = _recent_baseline(area_values, cfg.recent_frames, cfg.baseline_frames)
    if slices is not None:
        base_values, recent_values = slices
        base = statistics.median(base_values)
        recent = statistics.median(recent_values)
        if base > 0:
            drop = (base - recent) / base * 100
            if drop >= cfg.area_drop_critical_pct:
                findings.append(_finding(
                    "area-drop", "critical", zone,
                    f"area_px fell {drop:.1f}% vs the preceding {len(base_values)} "
                    f"frames (median {base:.0f} → {recent:.0f} px)",
                    value=drop, threshold=cfg.area_drop_critical_pct,
                ))
            elif drop >= cfg.area_drop_warn_pct:
                findings.append(_finding(
                    "area-drop", "warn", zone,
                    f"area_px fell {drop:.1f}% vs the preceding {len(base_values)} "
                    f"frames (median {base:.0f} → {recent:.0f} px)",
                    value=drop, threshold=cfg.area_drop_warn_pct,
                ))

    # 7b. solidity-drop
    solidity_values = [
        value for _ts, row in dated if (value := _num(row, "solidity")) is not None
    ]
    slices = _recent_baseline(solidity_values, cfg.recent_frames, cfg.baseline_frames)
    if slices is not None:
        base_values, recent_values = slices
        base = statistics.median(base_values)
        recent = statistics.median(recent_values)
        drop = base - recent
        if drop >= cfg.solidity_drop_critical:
            findings.append(_finding(
                "solidity-drop", "critical", zone,
                f"solidity fell {drop:.3f} (median {base:.3f} → {recent:.3f})",
                value=drop, threshold=cfg.solidity_drop_critical,
            ))
        elif drop >= cfg.solidity_drop_warn:
            findings.append(_finding(
                "solidity-drop", "warn", zone,
                f"solidity fell {drop:.3f} (median {base:.3f} → {recent:.3f})",
                value=drop, threshold=cfg.solidity_drop_warn,
            ))

    # 8. scale-coverage
    if len(dated) >= cfg.min_frames:
        mid = len(dated) // 2
        if mid >= 3:
            first_pct = _true_share([row for _ts, row in dated[:mid]])
            last_pct = _true_share([row for _ts, row in dated[mid:]])
            drop_pt = first_pct - last_pct
            if drop_pt >= cfg.scale_drop_critical_pt:
                findings.append(_finding(
                    "scale-coverage", "critical", zone,
                    f"scale-detected share fell {drop_pt:.1f} pt "
                    f"({first_pct:.1f}% → {last_pct:.1f}%)",
                    value=drop_pt, threshold=cfg.scale_drop_critical_pt,
                ))
            elif drop_pt >= cfg.scale_drop_warn_pt:
                findings.append(_finding(
                    "scale-coverage", "warn", zone,
                    f"scale-detected share fell {drop_pt:.1f} pt "
                    f"({first_pct:.1f}% → {last_pct:.1f}%)",
                    value=drop_pt, threshold=cfg.scale_drop_warn_pt,
                ))

    # 9. capture-gap
    timestamps = [ts for ts, _row in dated]
    if len(timestamps) >= 2:
        deltas = [
            (b - a).total_seconds() / 3600
            for a, b in zip(timestamps, timestamps[1:])
        ]
        gap_h = max(deltas)
        if gap_h >= cfg.gap_warn_hours:
            index = deltas.index(gap_h)
            start = timestamps[index]
            end = timestamps[index + 1]
            severity = "critical" if gap_h >= cfg.gap_critical_hours else "warn"
            threshold = (
                cfg.gap_critical_hours
                if severity == "critical"
                else cfg.gap_warn_hours
            )
            findings.append(_finding(
                "capture-gap", severity, zone,
                f"no frames for {gap_h:.1f} h between {_fmt_ts(start)} and "
                f"{_fmt_ts(end)}",
                value=gap_h, threshold=threshold,
                window_start=start.isoformat(), window_end=end.isoformat(),
            ))

    # 10. stale-data
    if dated:
        last = dated[-1][0]
        age_days = max(0.0, (now - last).total_seconds() / 86400)
        if age_days >= cfg.stale_warn_days:
            severity = "critical" if age_days >= cfg.stale_critical_days else "warn"
            threshold = (
                cfg.stale_critical_days
                if severity == "critical"
                else cfg.stale_warn_days
            )
            findings.append(_finding(
                "stale-data", severity, zone,
                f"last frame {_fmt_ts(last)} is {age_days:.1f} days old "
                f"(now {_fmt_ts(now)})",
                value=age_days, threshold=threshold,
            ))

    # 11. quality-flag-rate
    if dated:
        last = dated[-1][0]
        stale_note = (
            f" (as of {_fmt_ts(last)})"
            if last_age_days is not None
            and last_age_days * 24 > cfg.quality_window_hours
            else ""
        )
        window = [
            (ts, row) for ts, row in dated
            if ts >= last - timedelta(hours=cfg.quality_window_hours)
        ]
        if len(window) >= 5:
            flagged = sum(
                1 for _ts, row in window if quality_flags(row.get("quality_flag"))
            )
            rate = 100.0 * flagged / len(window)
            if rate >= cfg.quality_critical_pct:
                findings.append(_finding(
                    "quality-flag-rate", "critical", zone,
                    f"{flagged} of {len(window)} frames in the last "
                    f"{cfg.quality_window_hours:g} h carry quality flags"
                    f"{stale_note}",
                    value=rate, threshold=cfg.quality_critical_pct,
                ))
            elif rate >= cfg.quality_warn_pct:
                findings.append(_finding(
                    "quality-flag-rate", "warn", zone,
                    f"{flagged} of {len(window)} frames in the last "
                    f"{cfg.quality_window_hours:g} h carry quality flags"
                    f"{stale_note}",
                    value=rate, threshold=cfg.quality_warn_pct,
                ))

    # 12. camera-settings-change
    combinations: set[tuple[str, str, str]] = set()
    for row in zone_rows:
        parts = tuple(
            (row.get(key) or "").strip()
            for key in ("exposure_s", "white_balance", "gain_db")
        )
        if any(parts):
            combinations.add(parts)  # type: ignore[arg-type]
    distinct = sorted(combinations)
    if len(distinct) > 1:
        formatted = "; ".join(
            f"exposure_s={exposure},white_balance={balance},gain_db={gain}"
            for exposure, balance, gain in distinct[:3]
        )
        findings.append(_finding(
            "camera-settings-change", "warn", zone,
            f"{len(distinct)} distinct camera-setting combinations: {formatted}",
            value=float(len(distinct)), threshold=1.0,
        ))

    # 13. camera-settings-provenance
    if zone_rows:
        valid = sum(
            1 for row in zone_rows
            if (row.get("settings_source") or "").strip().lower()
            in {"exif", "app", "manual"}
        )
        pct = 100.0 * valid / len(zone_rows)
        if pct < cfg.settings_provenance_min_pct:
            findings.append(_finding(
                "camera-settings-provenance", "warn", zone,
                f"only {pct:.1f}% of {len(zone_rows)} rows record settings "
                "provenance (settings_source)",
                value=pct, threshold=cfg.settings_provenance_min_pct,
            ))

    return findings


def evaluate_rules(
    rows: Sequence[dict[str, str]],
    *,
    now: datetime,
    config: RuleConfig | None = None,
) -> list[Finding]:
    """Evaluate every rule per zone and return severity-sorted findings.

    Args:
        rows: Parsed CSV rows (string values throughout).
        now: Reference time for age/gap rules; a naive value is treated as UTC.
        config: Threshold overrides; defaults to :class:`RuleConfig`.

    Returns:
        Findings sorted critical first, then ``(zone, rule_id)``.

    Raises:
        TypeError: If ``now`` is not a datetime.
    """
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cfg = config or RuleConfig()
    findings: list[Finding] = []
    for zone, zone_rows in _zones(rows).items():
        findings.extend(_zone_findings(zone, zone_rows, now, cfg))
    return sorted(
        findings, key=lambda f: (SEVERITY_ORDER[f.severity], f.zone, f.rule_id)
    )
