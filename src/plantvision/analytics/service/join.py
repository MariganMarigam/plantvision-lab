"""Card, table, evidence and link assembly for the v3 payload.

B0 ships the section skeleton; B1 fills derivation, gating and the Crops /
Data-quality card joins.
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from plantvision.analytics.rules import RuleConfig

from .types import ServiceOptions, SourceBundle


def build_gate2(
    bundle: SourceBundle,
    *,
    now: datetime,
    options: ServiceOptions,
    config: RuleConfig | None,
    conditions: Mapping[str, object],
    validity: Mapping[str, object],
) -> dict[str, object]:
    """Assemble the v3 sections that need derived data.

    Args:
        bundle: Parsed sources.
        now: Resolved UTC reference time.
        options: Build options.
        config: Optional rule thresholds.
        conditions: Pre-built condition section.
        validity: Pre-built validity section.

    Returns:
        A dict with ``panels``, ``series``, ``measurements``, ``tables``,
        ``cards``, ``links``, ``findings`` and ``svgs``.
    """
    panels: list[dict[str, object]] = []
    for panel in bundle.panels:
        panel_id = str(getattr(panel, "id", ""))
        rows = bundle.rows_by_panel.get(panel_id, [])
        panels.append(
            {
                "id": panel_id,
                "label": str(getattr(panel, "label", "")),
                "crop": str(getattr(panel, "crop", "")),
                "method": str(getattr(panel, "method", "")),
                "method_label": str(getattr(panel, "method_label", "")),
                "pipeline_version": str(getattr(panel, "pipeline_version", "")),
                "source": str(getattr(panel, "csv_path", "")),
                "note": str(getattr(panel, "note", "")),
                "camera": (rows[0].get("camera_id", "") if rows else ""),
                "zone": (rows[0].get("zone_id", "") if rows else ""),
                "rows": len(rows),
                "days": 0,
                "first_at": "",
                "last_at": "",
                "span_hours": None,
                "age_days": None,
                "verdict": "unknown",
                "conditions": [],
                "kpi": {
                    "scale_pct": None,
                    "quality_pct": None,
                    "shape_pct": None,
                    "freshness_pct": None,
                },
                "quality": {"measured": False, "tokens": {}, "rate_pct": None},
                "shape": {"radar": [], "range": {}},
            }
        )
    return {
        "panels": panels,
        "series": {},
        "measurements": {},
        "tables": {},
        "cards": [],
        "links": {"cards": {}, "rules": {}, "aliases": {}},
        "findings": [],
        "svgs": {},
    }
