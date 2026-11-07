"""Validity gating before rules, plus the ``validity-violation`` finding.

Gating nulls metric cells only. ``captured_at``, ``quality_flag``, ``scale_ok``
and settings columns stay untouched so supply rules keep describing the
instrument honestly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Sequence

from plantvision.analytics.rules import (
    VALIDITY_RULE_ID,
    Finding,
    RuleConfig,
    evaluate_rules,
    parse_timestamp,
)
from plantvision.analytics.validity import ValidityTable, validity_state

from .derive import condition_key_for
from .types import GateState, SeriesBlock

_UTC = timezone.utc

SUPPLY_COLUMNS: frozenset[str] = frozenset(
    {
        "captured_at",
        "received_at",
        "quality_flag",
        "scale_ok",
        "sha256",
        "camera_id",
        "zone_id",
        "width",
        "height",
        "px_per_mm",
        "light_regime",
        "exposure_s",
        "white_balance",
        "gain_db",
        "settings_source",
        "experiment_id",
        "biosource_id",
        "observation_unit_id",
        "treatment_id",
    }
)

METRIC_COLUMNS: tuple[str, ...] = (
    "area_px",
    "area_cm2",
    "roi_fraction_pct",
    "solidity",
    "extent",
    "hull_area_px",
    "hull_area_cm2",
    "perimeter_px",
    "perimeter_cm",
    "ellipse_major_px",
    "ellipse_minor_px",
    "circularity",
)


@dataclass(frozen=True)
class GatedRow:
    """A row copy with invalid/unproven metric cells blanked."""

    row: dict[str, str]
    original: dict[str, str]
    condition_key: str
    states: Mapping[str, str] = field(default_factory=dict)


def resolve_series_state(state: str, measured: int) -> GateState:
    """Apply D25 precedence: invalid > unproven > empty > not_recorded > ok."""
    if state == "invalid":
        return GateState.INVALID
    if state == "unproven":
        return GateState.UNPROVEN
    if measured > 0:
        return GateState.OK
    return GateState.EMPTY


def gate_rows(
    rows: Sequence[dict[str, str]],
    validity: ValidityTable,
    *,
    method_version: str,
    panel: object,
) -> list[GatedRow]:
    """Blank metric cells whose tuple is invalid or unproven.

    Args:
        rows: Parsed CSV rows.
        validity: Loaded validity table.
        method_version: Panel pipeline version.
        panel: Panel definition (crop/pose/scale identity).

    Returns:
        One :class:`GatedRow` per input row, in source order. Rows are never
        deleted, only marked.
    """
    gated: list[GatedRow] = []
    for source in rows:
        condition = condition_key_for(panel, source)
        copy = dict(source)
        states: dict[str, str] = {}
        for metric in METRIC_COLUMNS:
            state = validity_state(validity, method_version, condition, metric)
            states[metric] = state
            if state in {"invalid", "unproven"} and metric in copy:
                copy[metric] = ""
        gated.append(
            GatedRow(
                row=copy,
                original=dict(source),
                condition_key=condition,
                states=states,
            )
        )
    return gated


def gate_series(block: SeriesBlock, state: GateState) -> SeriesBlock:
    """Return the series block with the resolved series state and draw mode."""
    draw = {
        GateState.INVALID: "hatch",
        GateState.UNPROVEN: "dashed",
        GateState.EMPTY: "none",
        GateState.NOT_RECORDED: "none",
        GateState.OK: "solid",
    }[state]
    return SeriesBlock(
        unit=block.unit,
        decimals=block.decimals,
        measured=block.measured,
        missing=block.missing,
        source_points=block.source_points,
        downsampled=block.downsampled,
        runs=block.runs,
        gaps=block.gaps,
        stats=block.stats,
        condition_key=block.condition_key,
        series_state=state.value,
        draw=draw,
        validity=block.validity,
    )


def _day_bounds(timestamp: datetime) -> tuple[datetime, datetime]:
    """UTC day start/end for one timestamp."""
    start = timestamp.astimezone(_UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start.replace(hour=23, minute=59, second=59)


def validity_findings(
    gated: Sequence[GatedRow],
    validity: ValidityTable,
    *,
    method_version: str,
    zone: str,
    config: RuleConfig | None = None,
) -> list[Finding]:
    """One ``validity-violation`` finding per method/condition/metric/day.

    Args:
        gated: Gated rows for one panel.
        validity: Loaded validity table.
        method_version: Panel pipeline version.
        zone: Panel zone label used in the finding.
        config: Optional severity thresholds.

    Returns:
        Findings sorted by severity, zone, day and metric.
    """
    cfg = config or RuleConfig()
    if not gated or validity.empty:
        return []
    condition = gated[0].condition_key
    relevant = [
        record
        for record in validity.records
        if record.method_version == method_version
        and record.condition_key == condition
        and record.status in {"invalid", "unproven"}
    ]
    findings: list[Finding] = []
    for record in relevant:
        groups: dict[str, tuple[datetime, datetime]] = {}
        for item in gated:
            timestamp = parse_timestamp(item.original.get("captured_at"))
            if timestamp is None:
                continue
            day = timestamp.astimezone(_UTC).date().isoformat()
            groups.setdefault(day, _day_bounds(timestamp))
        severity = (
            cfg.validity_violation_invalid_severity
            if record.status == "invalid"
            else cfg.validity_violation_unproven_severity
        )
        for day in sorted(groups):
            start, end = groups[day]
            findings.append(
                Finding(
                    rule_id=VALIDITY_RULE_ID,
                    severity=severity,
                    zone=zone,
                    detail=(
                        f"{record.metric} is {record.status} for "
                        f"{record.method_id}/{method_version} under "
                        f"{record.condition_key}; do not quote this metric"
                    ),
                    value=None,
                    threshold=None,
                    window_start=start.isoformat(),
                    window_end=end.isoformat(),
                )
            )
    return findings


def evaluate_gated_rules(
    gated: Sequence[GatedRow],
    now: datetime,
    config: RuleConfig | None = None,
    *,
    validity: ValidityTable | None = None,
    method_version: str = "",
    zone: str = "",
) -> list[Finding]:
    """Run value rules on gated rows, then append validity findings.

    Args:
        gated: Gated rows for one panel.
        now: Injected reference time.
        config: Optional rule thresholds.
        validity: Optional validity table for the new rule.
        method_version: Panel pipeline version.
        zone: Panel zone label.

    Returns:
        Findings sorted critical first, then ``(zone, rule_id, day)``.
    """
    findings = evaluate_rules(
        [item.row for item in gated], now=now, config=config
    )
    if validity is not None:
        findings.extend(
            validity_findings(
                gated,
                validity,
                method_version=method_version,
                zone=zone,
                config=config,
            )
        )
    return sorted(
        findings,
        key=lambda finding: (
            0 if finding.severity == "critical" else 1,
            finding.zone,
            finding.rule_id,
            finding.window_start,
        ),
    )
