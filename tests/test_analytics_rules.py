"""Unit tests for the pure rule engine (one case per rule + edge cases)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from plantvision.analytics.rules import (
    SEVERITY_ORDER,
    RuleConfig,
    evaluate_rules,
)
from plantvision.analytics.timeseries import TIMESERIES_COLUMNS

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def _row(**overrides: str) -> dict[str, str]:
    """Build a complete CSV row (real header keys) with sane defaults."""
    row = {column: "" for column in TIMESERIES_COLUMNS}
    row.update(
        {
            "sha256": "x",
            "captured_at": "2026-11-01T00:00:00Z",
            "zone_id": "z",
            "area_px": "1000",
            "scale_ok": "true",
        }
    )
    row.update(overrides)
    return row


def _series(
    values: list[float],
    start: str = "2026-10-31T00:00:00Z",
    step_min: int = 60,
) -> list[dict[str, str]]:
    """Build hourly rows whose ``area_px`` follows ``values``."""
    base = datetime.fromisoformat(start.replace("Z", "+00:00"))
    rows: list[dict[str, str]] = []
    for index, value in enumerate(values):
        captured = (base + timedelta(minutes=step_min * index)).isoformat()
        rows.append(
            _row(
                sha256=f"x{index}",
                captured_at=captured.replace("+00:00", "Z"),
                area_px=str(value),
            )
        )
    return rows


def _ids(findings: list) -> list[str]:
    """Return the rule ids in order."""
    return [finding.rule_id for finding in findings]


def test_empty_rows_returns_no_findings() -> None:
    assert evaluate_rules([], now=NOW) == []


def test_growth_stall_warns_on_flat_area() -> None:
    values = [1000 + (0.5 if index % 2 else -0.5) for index in range(12)]
    findings = evaluate_rules(_series(values), now=NOW)
    stalls = [finding for finding in findings if finding.rule_id == "growth-stall"]
    assert len(stalls) == 1
    assert stalls[0].severity == "warn"


def test_growth_stall_silent_when_growing() -> None:
    values = [1000 + 50 * index for index in range(12)]
    findings = evaluate_rules(_series(values), now=NOW)
    assert "growth-stall" not in _ids(findings)


def test_area_drop_warns_at_15_pct() -> None:
    values = [1000.0] * 9
    values[-3:] = [800.0, 800.0, 800.0]
    findings = evaluate_rules(_series(values), now=NOW)
    drops = [finding for finding in findings if finding.rule_id == "area-drop"]
    assert len(drops) == 1
    assert drops[0].severity == "warn"


def test_area_drop_critical_at_30_pct() -> None:
    values = [1000.0] * 9
    values[-3:] = [600.0, 600.0, 600.0]
    findings = evaluate_rules(_series(values), now=NOW)
    drops = [finding for finding in findings if finding.rule_id == "area-drop"]
    assert len(drops) == 1
    assert drops[0].severity == "critical"


def test_area_drop_ignores_single_frame_outlier() -> None:
    values = [1000.0] * 9
    values[2] = 200.0
    findings = evaluate_rules(_series(values), now=NOW)
    assert "area-drop" not in _ids(findings)


def test_solidity_drop_warn_and_critical() -> None:
    def with_solidity(last: str) -> list[dict[str, str]]:
        rows = _series([1000.0] * 9)
        for row in rows:
            row["solidity"] = "1.0"
        for row in rows[-3:]:
            row["solidity"] = last
        return rows

    warn = [
        finding for finding in evaluate_rules(with_solidity("0.9"), now=NOW)
        if finding.rule_id == "solidity-drop"
    ]
    critical = [
        finding for finding in evaluate_rules(with_solidity("0.8"), now=NOW)
        if finding.rule_id == "solidity-drop"
    ]
    assert warn and warn[0].severity == "warn"
    assert critical and critical[0].severity == "critical"


def test_solidity_drop_skipped_when_all_blank() -> None:
    findings = evaluate_rules(_series([1000.0] * 9), now=NOW)
    assert "solidity-drop" not in _ids(findings)


def test_scale_coverage_critical_when_marker_lost() -> None:
    rows = _series([1000.0] * 9)
    for row in rows[:4]:
        row["scale_ok"] = "true"
    for row in rows[4:]:
        row["scale_ok"] = "false"
    findings = [
        finding for finding in evaluate_rules(rows, now=NOW)
        if finding.rule_id == "scale-coverage"
    ]
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].value == pytest.approx(100.0)


def test_capture_gap_warn_and_critical() -> None:
    def gap_rows(hours: int) -> list[dict[str, str]]:
        start = datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(hours=hours)
        return [
            _row(captured_at=start.isoformat().replace("+00:00", "Z")),
            _row(
                captured_at=end.isoformat().replace("+00:00", "Z"),
                sha256="y",
            ),
        ]

    warn = [
        finding for finding in evaluate_rules(gap_rows(13), now=NOW)
        if finding.rule_id == "capture-gap"
    ]
    critical = [
        finding for finding in evaluate_rules(gap_rows(25), now=NOW)
        if finding.rule_id == "capture-gap"
    ]
    assert warn and warn[0].severity == "warn"
    assert critical and critical[0].severity == "critical"


def test_stale_data_critical_and_clamped_future() -> None:
    old = [_row(captured_at="2026-10-16T00:00:00Z")]
    stale = [
        finding for finding in evaluate_rules(old, now=NOW)
        if finding.rule_id == "stale-data"
    ]
    assert stale and stale[0].severity == "critical"

    future = [_row(captured_at="2026-12-01T00:00:00Z")]
    findings = evaluate_rules(future, now=NOW)
    assert "stale-data" not in _ids(findings)


def test_quality_flag_rate_ignores_blank_and_ok() -> None:
    rows = _series([1000.0] * 10)
    rows[0]["quality_flag"] = "blur"
    rows[1]["quality_flag"] = "ok"
    findings = [
        finding for finding in evaluate_rules(rows, now=NOW)
        if finding.rule_id == "quality-flag-rate"
    ]
    assert findings and findings[0].severity == "warn"


def test_quality_flag_counts_row_once_for_multiple_tokens() -> None:
    rows = _series([1000.0] * 10)
    rows[0]["quality_flag"] = "blur|dark"
    findings = [
        finding for finding in evaluate_rules(rows, now=NOW)
        if finding.rule_id == "quality-flag-rate"
    ]
    assert findings and findings[0].value == pytest.approx(10.0)


def test_camera_settings_change_warns_on_two_combinations() -> None:
    rows = [
        _row(exposure_s="0.01"),
        _row(sha256="y", exposure_s="0.02"),
    ]
    findings = [
        finding for finding in evaluate_rules(rows, now=NOW)
        if finding.rule_id == "camera-settings-change"
    ]
    assert findings and findings[0].severity == "warn"


def test_camera_settings_provenance_warns_when_blank() -> None:
    findings = [
        finding for finding in evaluate_rules(_series([1000.0] * 6), now=NOW)
        if finding.rule_id == "camera-settings-provenance"
    ]
    assert findings and findings[0].severity == "warn"


def test_unparseable_timestamps_are_skipped_without_crash() -> None:
    rows = [
        _row(captured_at="not-a-date"),
        _row(sha256="y", captured_at=""),
    ]
    findings = evaluate_rules(rows, now=NOW)
    time_rules = {
        "growth-stall", "area-drop", "solidity-drop", "scale-coverage",
        "capture-gap", "stale-data", "quality-flag-rate",
    }
    assert time_rules.isdisjoint(_ids(findings))


def test_custom_config_thresholds_are_honored() -> None:
    start = datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)
    rows = [
        _row(captured_at=start.isoformat().replace("+00:00", "Z")),
        _row(captured_at=end.isoformat().replace("+00:00", "Z"), sha256="y"),
    ]
    findings = evaluate_rules(
        rows, now=NOW, config=RuleConfig(gap_warn_hours=1.0)
    )
    assert "capture-gap" in _ids(findings)


def test_findings_sorted_critical_before_warn() -> None:
    rows = [_row(captured_at="2026-10-01T00:00:00Z")]
    findings = evaluate_rules(rows, now=NOW)
    assert findings[0].severity == "critical"
    assert any(finding.severity == "warn" for finding in findings)
    order = [SEVERITY_ORDER[finding.severity] for finding in findings]
    assert order == sorted(order)


def test_findings_grouped_by_zone() -> None:
    rows = [
        _row(zone_id="a", captured_at="2026-10-01T00:00:00Z"),
        _row(zone_id="b", sha256="y", captured_at="2026-10-01T00:00:00Z"),
    ]
    findings = evaluate_rules(rows, now=NOW)
    assert {finding.zone for finding in findings} == {"a", "b"}


def test_time_relative_rules_state_as_of_when_data_is_stale() -> None:
    """A 24 h statement on 16-day-old data must carry its real as-of date."""
    values = [1000 + (0.5 if index % 2 else -0.5) for index in range(12)]
    rows = _series(values, start="2026-10-16T00:00:00Z")
    for row in rows:
        row["quality_flag"] = "red"

    findings = evaluate_rules(rows, now=NOW)
    stalls = [f for f in findings if f.rule_id == "growth-stall"]
    quality = [f for f in findings if f.rule_id == "quality-flag-rate"]
    assert stalls and "(as of " in stalls[0].detail
    assert quality and "(as of " in quality[0].detail
    assert "over the last 24 h" in stalls[0].detail

