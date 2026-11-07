"""Orchestration for the versioned analytics payload.

The public entry point is :func:`build_payload`. It composes the pure service
modules and never performs I/O itself.
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from plantvision.analytics.dashboard.contract import RENDER
from plantvision.analytics.dashboard.model import build_payload as legacy_build_payload
from plantvision.analytics.rules import RuleConfig
from plantvision.analytics.validity import (
    CONDITION_ORDER,
    build_matrix,
    condition_key,
    validity_state,
)

from .load import load_sources
from .types import Gate2Bundle, ServiceOptions, SourcePaths, SourceBundle
from .validate import SCHEMA, SCHEMA_MINOR, validate_payload, validate_sources

_UTC = timezone.utc
_MAX_JSON_BYTES = 320_000
_ALIASES: dict[str, str] = {
    "ch-gr-area-px": "cd-area-line",
    "ch-dq-scale-stacked": "dq-scale-stacked",
    "ch-dq-scale-ring": "dq-scale-ring",
    "ch-dq-quality-bars": "dq-quality-bars",
    "ch-dq-gap-bars": "dq-gap-bars",
    "ch-dq-provenance-heatmap": "dq-provenance-heatmap",
    "ch-ov-kpi-rings": "cd-kpi-rings",
}


def _iso_z(moment: datetime) -> str:
    """ISO-8601 UTC string with the trailing ``Z``."""
    return moment.astimezone(_UTC).isoformat().replace("+00:00", "Z")


def _resolve_now(now: datetime | None, bundle: SourceBundle) -> tuple[datetime, str]:
    """Resolve the clock; a naive value is treated as UTC."""
    if now is not None:
        value = now if now.tzinfo else now.replace(tzinfo=_UTC)
        return value.astimezone(_UTC), "cli"
    latest: datetime | None = None
    for rows in bundle.raw_rows_by_panel.values():
        for row in rows:
            raw = (row.get("captured_at") or "").strip()
            if not raw:
                continue
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=_UTC)
            if latest is None or parsed > latest:
                latest = parsed
    if latest is None:
        return datetime(1970, 1, 1, tzinfo=_UTC), "none"
    return latest.astimezone(_UTC), "data"


def panel_condition(panel: object, row: Mapping[str, str]) -> str:
    """Compose the canonical condition key for a panel row."""
    camera = (row.get("camera_id") or "").strip()
    scale_ok = (row.get("scale_ok") or "").strip().lower() in {"true", "1", "yes"}
    pose = str(getattr(panel, "pose", "") or "side")
    return condition_key(
        {
            "light": (row.get("light_regime") or "").strip(),
            "crop": str(getattr(panel, "crop", "") or ""),
            "rig": camera,
            "scale": "aruco45" if scale_ok else "none",
            "pose": pose,
        }
    )


def _condition_section(bundle: SourceBundle) -> dict[str, object]:
    """Build ``conditions`` from every raw row, without filtering."""
    regimes: dict[str, dict[str, object]] = {}
    for panel in bundle.panels:
        panel_id = str(getattr(panel, "id", ""))
        for row in bundle.raw_rows_by_panel.get(panel_id, []):
            cond = panel_condition(panel, row)
            entry = regimes.setdefault(
                cond,
                {
                    "light": (row.get("light_regime") or "").strip(),
                    "crop": str(getattr(panel, "crop", "")),
                    "rig": (row.get("camera_id") or "").strip(),
                    "scale": "aruco45"
                    if (row.get("scale_ok") or "").strip().lower() in {"true", "1", "yes"}
                    else "none",
                    "pose": str(getattr(panel, "pose", "") or "side"),
                    "rows": 0,
                    "first_at": "",
                    "last_at": "",
                    "_px": [],
                },
            )
            entry["rows"] = int(entry["rows"]) + 1
            raw = (row.get("captured_at") or "").strip()
            if raw:
                entry["first_at"] = min(str(entry["first_at"] or raw), raw)
                entry["last_at"] = max(str(entry["last_at"] or raw), raw)
            if (row.get("scale_ok") or "").strip().lower() in {"true", "1", "yes"}:
                try:
                    px = float((row.get("px_per_mm") or "").strip())
                except ValueError:
                    px = math.nan
                if math.isfinite(px):
                    entry["_px"].append(px)  # type: ignore[index]
    keys = sorted(regimes)
    clean: dict[str, dict[str, object]] = {}
    for key in keys:
        entry = dict(regimes[key])
        px = entry.pop("_px", [])
        entry["px_per_mm_median"] = (
            round(float(statistics.median(px)), 4) if px else None
        )
        clean[key] = entry
    switch_at: str | None = None
    dated: list[tuple[datetime, str]] = []
    seen: set[tuple[str, str]] = set()
    for panel in bundle.panels:
        panel_id = str(getattr(panel, "id", ""))
        for row in bundle.raw_rows_by_panel.get(panel_id, []):
            raw = (row.get("captured_at") or "").strip()
            light = (row.get("light_regime") or "").strip()
            if not raw or (raw, light) in seen:
                continue
            seen.add((raw, light))
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=_UTC)
            dated.append((parsed, light))
    dated.sort(key=lambda pair: pair[0])
    for (_previous_ts, previous_light), (current_ts, current_light) in zip(dated, dated[1:]):
        if current_light and previous_light and current_light != previous_light:
            switch_at = _iso_z(current_ts)
    return {
        "order": list(CONDITION_ORDER),
        "keys": keys,
        "regimes": clean,
        "switch_at": switch_at,
    }


def _validity_section(bundle: SourceBundle) -> dict[str, object]:
    """Serialise the validity table into the four payload blocks."""
    table = bundle.validity
    return {
        "rows": [record.as_json() for record in table.records],
        "by_key": dict(table.by_key),
        "matrix": build_matrix(table),
        "counts": table.counts(),
    }


def _evidence_section(bundle: SourceBundle) -> dict[str, object]:
    """Emit csv/config/validity evidence ids with relative paths."""
    evidence: dict[str, object] = {}
    for panel in bundle.panels:
        panel_id = str(getattr(panel, "id", ""))
        csv_path = str(getattr(panel, "csv_path", ""))
        rows = len(bundle.rows_by_panel.get(panel_id, []))
        evidence[f"ev:csv:{panel_id}"] = {
            "kind": "csv",
            "path": csv_path,
            "selector": "",
            "rows": rows,
            "validity_row": None,
            "frame_sha": None,
        }
        evidence[f"ev:config:{panel_id}"] = {
            "kind": "config",
            "path": "configs/dashboard-panels.yaml",
            "selector": panel_id,
            "rows": None,
            "validity_row": None,
            "frame_sha": None,
        }
        for metric in ("area_px", "area_cm2", "solidity", "scale_ok", "quality_flag", "captured_at"):
            evidence[f"ev:csv:{panel_id}:{metric}"] = {
                "kind": "csv",
                "path": csv_path,
                "selector": metric,
                "rows": rows,
                "validity_row": None,
                "frame_sha": None,
            }
    for record in bundle.validity.records:
        evidence[record.evidence_id] = {
            "kind": "validity",
            "path": record.evidence_path or "data/derived/validity.csv",
            "selector": f"{record.method_id}|{record.condition_key}|{record.metric}",
            "rows": record.evidence_rows,
            "validity_row": record.key,
            "frame_sha": None,
        }
    evidence["ev:alerts"] = {
        "kind": "csv",
        "path": "data/derived/alerts.json",
        "selector": "",
        "rows": None,
        "validity_row": None,
        "frame_sha": None,
    }
    return evidence


def _legacy_findings(payload: Mapping[str, object]) -> list[dict[str, object]]:
    """Copy and enrich the v2 findings with v3 linkage keys."""
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return []
    enriched: list[dict[str, object]] = []
    for item in findings:
        if not isinstance(item, Mapping):
            continue
        block = dict(item)
        block.setdefault("evidence_id", "ev:alerts")
        block.setdefault("cards", [])
        block.setdefault("span", None)
        block["rule_version"] = "rules/1"
        enriched.append(block)
    return enriched


def _snapshots(payload: Mapping[str, object]) -> dict[str, object]:
    """Deterministic snapshot values: sorted dotted paths to scalar leaves."""
    values: dict[str, object] = {}
    for key, value in sorted(payload.items()):
        if key in {"snapshots", "legacy", "render", "cards", "evidence"}:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values[key] = value
    return {
        "format": "pv-snapshot/3",
        "generated_at": str(payload.get("meta", {}).get("now", "")),
        "filters": dict(payload.get("meta", {}).get("options", {})),
        "values": values,
    }


def _render_section() -> dict[str, object]:
    """Static render constants the client may read."""
    return {
        **RENDER,
        "tabs": [
            "overview",
            "crops",
            "growth",
            "shape",
            "data-quality",
            "alerts",
            "compare",
            "capture",
            "method",
        ],
        "subs": {"data-quality": ["scale", "quality-flags", "gaps", "provenance"]},
        "primitives": [
            "line", "bars", "stacked", "ring", "radar", "strips", "calendar",
            "small-multiples", "box", "scatter", "validity-matrix", "table",
        ],
        "states": ["ok", "empty", "not_recorded", "invalid", "unproven"],
        "colors": {"A": "#F5705E", "B": "#C159F5", "pos": "#2FE3A7"},
        "version": "render/3",
    }


def build_gate2_bundle(
    panels: Sequence[object],
    now: datetime | None,
    options: ServiceOptions,
    *,
    config: RuleConfig | None = None,
    sources: SourcePaths | None = None,
) -> Gate2Bundle:
    """Build the v3 sections, cards and SVG map for a page build.

    This is the internal boundary used by ``dashboard.build.build_report``; the
    public contract is :func:`build_payload`.
    """
    if not panels:
        raise ValueError("at least one panel is required")
    ids = [str(getattr(panel, "id", "")) for panel in panels]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate panel id")
    bundle = load_sources(panels, sources or SourcePaths(), now=now)
    validate_sources(bundle)
    now_utc, now_source = _resolve_now(now, bundle)
    legacy = legacy_build_payload(
        panels, now=now_utc, title=options.title, config=config
    )
    conditions = _condition_section(bundle)
    validity = _validity_section(bundle)
    evidence = _evidence_section(bundle)
    # B1 fills cards/series/tables; B0 exposes the contract skeleton.
    gate2 = _gate2_sections(bundle, now_utc, now_source, options, config, conditions, validity)
    cards = gate2["cards"]
    sections: dict[str, object] = {
        "meta": {
            "schema": SCHEMA,
            "schema_minor": SCHEMA_MINOR,
            "title": options.title,
            "lang": options.lang,
            "now": _iso_z(now_utc),
            "generated_at": _iso_z(now_utc) if now_source == "cli" else None,
            "now_source": now_source,
            "options": {
                "window": options.window,
                "agg": options.agg,
                "mode": options.mode,
            },
            "totals": {
                "panels": len(panels),
                "rows": sum(len(rows) for rows in bundle.rows_by_panel.values()),
                "days": int(legacy["totals"]["days"]),
                "first_at": str(legacy["totals"]["first_at"]),
                "last_at": str(legacy["totals"]["last_at"]),
                "critical": sum(
                    1 for item in gate2["findings"] if item.get("severity") == "critical"
                ),
                "warn": sum(
                    1 for item in gate2["findings"] if item.get("severity") == "warn"
                ),
            },
            "budget": {"json_bytes": 0, "max_json_bytes": _MAX_JSON_BYTES},
        },
        "conditions": conditions,
        "panels": gate2["panels"],
        "series": gate2["series"],
        "measurements": gate2["measurements"],
        "validity": validity,
        "evidence": evidence,
        "tables": gate2["tables"],
        "cards": cards,
        "links": gate2["links"],
        "findings": gate2["findings"],
        "snapshots": {},
        "render": _render_section(),
    }
    sections["snapshots"] = _snapshots(sections)
    size = len(
        json.dumps(sections, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )
    sections["meta"]["budget"] = {  # type: ignore[index]
        "json_bytes": size,
        "max_json_bytes": _MAX_JSON_BYTES,
    }
    payload = {**sections, "legacy": legacy}
    validate_payload(payload)
    return Gate2Bundle(
        sections=sections,
        cards=cards,
        svgs=gate2["svgs"],
        findings=gate2["findings"],
        legacy=legacy,
    )


def _gate2_sections(
    bundle: SourceBundle,
    now: datetime,
    now_source: str,
    options: ServiceOptions,
    config: RuleConfig | None,
    conditions: Mapping[str, object],
    validity: Mapping[str, object],
) -> dict[str, object]:
    """Populate the v3 sections; B1 adds derivation and card joins."""
    from .join import build_gate2

    return build_gate2(
        bundle,
        now=now,
        options=options,
        config=config,
        conditions=conditions,
        validity=validity,
    )


def build_payload(
    panels: Sequence[object],
    now: datetime,
    options: ServiceOptions,
    *,
    config: RuleConfig | None = None,
    sources: SourcePaths | None = None,
) -> dict[str, object]:
    """Build the versioned payload.

    Args:
        panels: Panel definitions from ``configs/dashboard-panels.yaml``.
        now: Mandatory reference time; a naive value is treated as UTC.
        options: Filter/language/point-budget options.
        config: Optional rule thresholds.
        sources: Optional repository-relative source paths.

    Returns:
        The ``pv-dashboard/3`` payload with the v2 compatibility mirror under
        ``legacy``.
    """
    bundle = build_gate2_bundle(
        panels, now, options, config=config, sources=sources
    )
    return {**bundle.sections, "legacy": bundle.legacy}
