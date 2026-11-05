"""Shared contract for client-rendered charts, filters and the snapshot."""

from __future__ import annotations

from typing import Sequence

RENDER: dict[str, int] = {
    "w": 720,
    "h": 240,
    "hm": 266,
    "pl": 52,
    "pt": 18,
    "pr": 18,
    "pb": 40,
    "pw": 650,
    "ph": 182,
    "legendY": 258,
    "xLabelY": 226,
    "xTitleY": 238,
    "lastX": 700,
    "tickY": 30,
}

FILTERS: dict[str, tuple[str, ...]] = {
    "windows": ("24h", "7d", "30d", "all"),
    "aggs": ("raw", "hourly", "daily"),
    "modes": ("abs", "idx", "delta"),
}


def crops_payload(panels: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    """Ordered unique crop list with the panels and rows behind each crop.

    Args:
        panels: Panel payload blocks in config order.

    Returns:
        One entry per crop, in first-seen order.
    """
    seen: dict[str, dict[str, object]] = {}
    for panel in panels:
        name = str(panel.get("crop") or "").strip()
        if not name:
            continue
        if name not in seen:
            seen[name] = {"name": name, "panels": [], "rows": 0, "last_at": ""}
        entry = seen[name]
        panel_id = str(panel.get("id", ""))
        if panel_id:
            panels_list = entry["panels"]
            if isinstance(panels_list, list):
                panels_list.append(panel_id)
        try:
            rows = int(panel.get("rows", 0) or 0)
        except (TypeError, ValueError):
            rows = 0
        entry["rows"] = int(entry["rows"]) + rows
        entry["last_at"] = max(str(entry["last_at"]), str(panel.get("last_at", "")))
    return list(seen.values())
