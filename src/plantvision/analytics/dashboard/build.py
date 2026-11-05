"""Build orchestration: config -> payload -> SVG map -> page -> byte gate."""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

import yaml

from plantvision.analytics.rules import Finding, RuleConfig, evaluate_rules

from . import frames as frame_tools
from . import layout
from .charts import (
    BarItem,
    ChartSpec,
    DonutSegment,
    PlotSeries,
    StripRow,
    Threshold,
    bar_chart,
    donut,
    line_chart,
    ring,
    strips,
)
from .copy import PER_PANEL_CONCLUSION, TEXTS, cards_for_payload
from .legacy import load_rows
from .model import build_payload, resolve_now
from .svg import esc

_ID_RE = re.compile(r"^[a-z0-9-]+$")
_SLOTS = ("A", "B", "C")


@dataclass(frozen=True)
class Panel:
    """One configured store."""

    id: str
    label: str
    crop: str
    method: str
    method_label: str
    csv_path: Path
    frames_dir: Path | None = None
    masks_dir: Path | None = None
    pipeline_version: str = "unrecorded"
    note: str = ""


@dataclass(frozen=True)
class ReportResult:
    """What one :func:`build_report` call produced."""

    out_path: Path
    panels: int
    rows_total: int
    days: int
    findings: tuple[Finding, ...]
    charts: int
    frames: int
    bytes_total: int
    json_bytes: int
    now_source: str


def load_panels(path: Path) -> list[Panel]:
    """Load and validate the panel config.

    Args:
        path: YAML config path.

    Returns:
        Panel definitions in config order.

    Raises:
        FileNotFoundError: If the config file is missing.
        ValueError: For an empty list, missing keys, or duplicate/invalid ids.
        yaml.YAMLError: For malformed YAML (propagated).
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"panels config not found: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("panels config is empty")
    entries = data.get("panels")
    if not isinstance(entries, list) or not entries:
        raise ValueError("panels config is empty")
    panels: list[Panel] = []
    seen: set[str] = set()
    required = ("id", "label", "crop", "method", "method_label", "csv")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("panel entry must be a mapping")
        for key in required:
            if not str(entry.get(key, "")).strip():
                raise ValueError(f"panel is missing {key}")
        panel_id = str(entry["id"]).strip()
        if not _ID_RE.match(panel_id):
            raise ValueError(f"invalid panel id: {panel_id}")
        if panel_id in seen:
            raise ValueError(f"duplicate panel id: {panel_id}")
        seen.add(panel_id)
        frames_dir = str(entry.get("frames_dir") or "").strip()
        masks_dir = str(entry.get("masks_dir") or "").strip()
        panels.append(
            Panel(
                id=panel_id,
                label=str(entry["label"]),
                crop=str(entry["crop"]),
                method=str(entry["method"]),
                method_label=str(entry["method_label"]),
                csv_path=Path(str(entry["csv"])),
                frames_dir=Path(frames_dir) if frames_dir else None,
                masks_dir=Path(masks_dir) if masks_dir else None,
                pipeline_version=str(entry.get("pipeline_version") or "unrecorded"),
                note=str(entry.get("note") or ""),
            )
        )
    return panels


def _weighted(average: float | None, weight: int, total: int, accumulated: float) -> float:
    """Accumulate a weighted percentage."""
    if average is None or total <= 0:
        return accumulated
    return accumulated + average * weight


def _svg_for(
    payload: dict[str, object],
    frames: dict[str, str],
    lang: str = "en",
    *,
    static_growth: bool = True,
) -> dict[str, str]:
    """Render the SVG map for every chart card in the payload.

    Args:
        payload: Page payload with ``cards`` filled.
        frames: Frame asset map (unused by gate-1 cards).
        lang: Initial language for the few labelled chart fragments.
        static_growth: Keep the Python-rendered Growth fallback charts.

    Returns:
        ``card_id -> markup``; table/board cards are absent.
    """
    panels = payload.get("panels") if isinstance(payload.get("panels"), list) else []
    cards = payload.get("cards") if isinstance(payload.get("cards"), list) else []
    calendar = payload.get("calendar") if isinstance(payload.get("calendar"), dict) else {}
    svgs: dict[str, str] = {}
    for card in cards:
        card_id = str(card["id"])
        kind = str(card.get("chart", ""))
        title = str(card.get("title_en", ""))
        desc = f"{card.get('what_en', '')} {card.get('now_en', '')}".strip()
        if card_id.startswith("ch-gr-") and not static_growth:
            continue
        if kind in {"table", "board", "image"}:
            continue
        if card_id == "ch-ov-last-change":
            plot_series = [
                PlotSeries(
                    _SLOTS[index % 3],
                    [
                        [
                            (int(pair[0]), float(pair[1]))
                            for pair in panel.get("last_change", [])
                        ]
                    ]
                    if panel.get("last_change")
                    else [],
                    label=str(panel.get("label", "")),
                )
                for index, panel in enumerate(panels)
                if panel.get("last_change")
            ]
            svgs[card_id] = line_chart(
                ChartSpec(card_id, title, desc, unit="index", decimals=1),
                plot_series,
                thresholds=(
                    Threshold(102.0, "+2 %", "warn"),
                    Threshold(98.0, "−2 %", "critical"),
                ),
                width=720,
                height=240,
            )
            continue
        if kind == "line":
            key = "area_cm2" if card_id == "ch-gr-area-cm2" else "area_px"
            first_series = (
                panels[0].get("series", {}).get(key, {}) if panels else {}
            )
            unit = str(first_series.get("unit", ""))
            decimals = int(first_series.get("decimals", 1))
            plot_series = [
                PlotSeries(
                    _SLOTS[index % 3],
                    panel.get("series", {}).get(key, {}).get("runs", []),
                    label=str(panel.get("label", "")),
                )
                for index, panel in enumerate(panels)
            ]
            missing: list[int] = []
            if key == "area_cm2":
                for panel in panels:
                    missing.extend(int(value) for value in panel.get("scale_missing", []))
            spec = ChartSpec(card_id, title, desc, unit=unit, decimals=decimals)
            thresholds: list[Threshold] = []
            if key == "area_px":
                values = [
                    value
                    for panel in panels
                    for run in panel.get("series", {}).get("area_px", {}).get("runs", [])
                    for _timestamp, value in run
                ]
                if values:
                    ordered = sorted(values)
                    median = ordered[len(ordered) // 2]
                    thresholds.append(
                        Threshold(median, f"{median:,.0f}", "warn")
                    )
            svgs[card_id] = line_chart(
                spec,
                plot_series,
                thresholds=tuple(thresholds),
                missing=tuple(sorted(set(missing))),
            )
            continue
        if kind == "bars-grouped":
            days = [
                str(cell.get("date", ""))
                for cell in (calendar.get("rows", [{}])[0].get("cells", []) if calendar.get("rows") else [])
            ]
            daily_by_panel = {
                str(panel.get("id")): {
                    str(bucket.get("date")): int(bucket.get("frames", 0))
                    for bucket in panel.get("daily", [])
                }
                for panel in panels
            }
            items: list[BarItem] = []
            for day in days:
                for panel in panels:
                    items.append(
                        BarItem(
                            label=day[5:],
                            value=float(daily_by_panel[str(panel.get("id"))].get(day, 0)),
                        )
                    )
            spec = ChartSpec(card_id, title, desc, unit="frames", decimals=0)
            svgs[card_id] = bar_chart(
                spec,
                items,
                height=220,
                group_size=max(1, len(panels)),
                series_labels=[str(panel.get("label", "")) for panel in panels],
            )
            continue
        if kind == "rings":
            rows_total = sum(int(panel.get("rows", 0)) for panel in panels)
            scale = 0.0
            shape = 0.0
            shape_weight = 0
            freshness: float | None = None
            for panel in panels:
                kpi = panel.get("kpi") if isinstance(panel.get("kpi"), dict) else {}
                weight = int(panel.get("rows", 0))
                scale = _weighted(kpi.get("scale_pct"), weight, rows_total, scale)
                if kpi.get("shape_pct") is not None:
                    shape = _weighted(kpi.get("shape_pct"), weight, rows_total, shape)
                    shape_weight += weight
                value = kpi.get("freshness_pct")
                if value is not None and (freshness is None or value < freshness):
                    freshness = float(value)
            scale_value = 100.0 * scale / rows_total if rows_total else None
            shape_value = 100.0 * shape / shape_weight if shape_weight else None
            critical = sum(int(panel.get("alerts", {}).get("critical", 0)) for panel in panels)
            warn = sum(int(panel.get("alerts", {}).get("warn", 0)) for panel in panels)
            pressure = (
                100.0 * (1.0 - (3 * critical + warn) / (3 * max(1, rows_total)))
                if rows_total
                else None
            )
            ring_values = (
                ("scale", scale_value),
                ("freshness", freshness),
                ("pressure", pressure),
                ("shape", shape_value),
            )
            fragments: list[str] = []
            for key, value in ring_values:
                label_en = TEXTS["en"][f"ui.ring.{key}"]
                label_ru = TEXTS["ru"][f"ui.ring.{key}"]
                active_label = label_en if lang == "en" else label_ru
                span = (
                    f'<span class="pv-ring-lbl" data-en="{esc(label_en)}" '
                    f'data-ru="{esc(label_ru)}">{esc(active_label)}</span>'
                )
                markup = ring(
                    value,
                    label=active_label,
                    chart_id=f"{card_id}-{key}",
                ).replace(
                    f'<span class="pv-ring-lbl">{esc(active_label)}</span>', span
                )
                fragments.append(markup)
            svgs[card_id] = '<div class="pv-ringrow">' + "".join(fragments) + "</div>"
            continue
        if kind == "donut":
            findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
            critical = sum(1 for finding in findings if finding.get("severity") == "critical")
            warn = sum(1 for finding in findings if finding.get("severity") == "warn")
            ok = max(0, len(findings) - critical - warn)
            segments = (
                DonutSegment("critical", float(critical), "critical"),
                DonutSegment("warn", float(warn), "warn"),
                DonutSegment("ok", float(ok), "ok"),
            )
            svgs[card_id] = donut(segments, centre="", chart_id=card_id)
            continue
        if kind == "strips":
            rows = []
            for panel in panels:
                cells: list[float | None] = []
                for bucket in panel.get("daily", []):
                    frames_count = int(bucket.get("frames", 0))
                    cells.append(float(frames_count) if frames_count > 0 else None)
                rows.append(StripRow(str(panel.get("label", "")), cells))
            svgs[card_id] = strips(
                ChartSpec(card_id, title, desc, unit="frames", decimals=0), rows
            )
            continue
        if kind == "bars-diverging":
            items = []
            units = set()
            for panel in panels:
                daily = panel.get("daily", [])
                cm2 = [
                    float(bucket["median_area_cm2"])
                    for bucket in daily
                    if bucket.get("median_area_cm2") is not None
                ]
                px = [
                    float(bucket["median_area_px"])
                    for bucket in daily
                    if bucket.get("median_area_px") is not None
                ]
                series = cm2 if len(cm2) >= 2 else px
                units.add("cm²" if series is cm2 else "px")
                value = series[-1] - series[-2] if len(series) >= 2 else None
                items.append(BarItem(str(panel.get("label", "")), value))
            unit = "cm²" if units == {"cm²"} else "px"
            svgs[card_id] = bar_chart(
                ChartSpec(card_id, title, desc, unit=unit, decimals=2),
                items,
                diverging=True,
            )
            continue
        if kind in {"bars", "area"}:
            items = []
            for bucket_index, bucket in enumerate(
                (panels[0].get("daily", []) if panels else [])
            ):
                for panel in panels:
                    daily = panel.get("daily", [])
                    if bucket_index >= len(daily):
                        continue
                    median = daily[bucket_index].get("median_area_px")
                    items.append(
                        BarItem(
                            label=str(daily[bucket_index].get("date", ""))[5:],
                            value=None if median is None else float(median),
                        )
                    )
            if not items:
                continue
            svgs[card_id] = bar_chart(
                ChartSpec(card_id, title, desc, unit="px", decimals=0),
                items,
                group_size=max(1, len(panels)),
                series_labels=[str(panel.get("label", "")) for panel in panels],
            )
            continue
    return svgs


def _frame_assets(
    panels: Sequence[Panel],
    rows_by_panel: dict[str, list[dict[str, str]]],
    *,
    include: bool,
    width: int,
    quality: int,
) -> tuple[dict[str, str], list[dict[str, object]]]:
    """Render deterministic thumbnails and (optionally) a mask overlay.

    Args:
        panels: Panel definitions.
        rows_by_panel: Parsed rows keyed by panel id.
        include: When ``False``, return empty results.
        width: Thumbnail width.
        quality: Initial JPEG quality.

    Returns:
        ``(assets, records)``; ``assets`` maps frame id to a data URI.
    """
    if not include:
        return {}, []
    assets: dict[str, str] = {}
    records: list[dict[str, object]] = []
    budget = 300_000
    used = 0
    for panel in panels:
        if panel.frames_dir is None or not panel.frames_dir.is_dir():
            continue
        index = frame_tools.index_frames(panel.frames_dir)
        selected = frame_tools.select_frames(rows_by_panel.get(panel.id, []), index)
        for position, row in enumerate(selected):
            sha = str(row.get("sha256", ""))
            path = index.get(sha[:16])
            if path is None:
                continue
            current_quality = quality
            try:
                encoded = frame_tools.render_thumb(path, width=width, quality=current_quality)
            except ValueError:
                continue
            if used + len(encoded) > budget:
                try:
                    encoded = frame_tools.render_thumb(path, width=width, quality=45)
                except ValueError:
                    continue
            if used + len(encoded) > budget:
                break
            used += len(encoded)
            frame_id = f"f{len(records)}"
            assets[frame_id] = (
                "data:image/jpeg;base64," + base64.b64encode(encoded).decode("ascii")
            )
            record: dict[str, object] = {
                "id": frame_id,
                "panel": panel.id,
                "sha256": sha,
                "captured_at": str(row.get("captured_at", "")),
                "index": position,
                "total": len(selected),
                "caption": f"{panel.label} · {str(row.get('captured_at', ''))[:16]}",
                "alt": frame_tools.frame_alt(
                    panel.label, str(row.get("captured_at", "")), position, len(selected)
                ),
            }
            if (
                panel.masks_dir is not None
                and position == len(selected) - 1
            ):
                mask_path = panel.masks_dir / f"{sha}.png"
                if mask_path.is_file():
                    try:
                        overlay = frame_tools.render_mask_overlay(path, mask_path)
                    except ValueError:
                        overlay = b""
                    if overlay:
                        mask_id = f"{frame_id}m"
                        assets[mask_id] = (
                            "data:image/jpeg;base64,"
                            + base64.b64encode(overlay).decode("ascii")
                        )
                        record["mask"] = mask_id
            records.append(record)
    return assets, records


def build_report(
    panels: Sequence[Panel],
    out_path: Path,
    *,
    now: datetime | None,
    title: str,
    thumb_width: int = 288,
    thumb_quality: int = 58,
    include_frames: bool = True,
    max_bytes: int = 1_048_576,
    config: RuleConfig | None = None,
    lang: str = "en",
    static_growth: bool = True,
    max_json_bytes: int = 256_000,
) -> ReportResult:
    """Build the page and write it atomically after the byte gate.

    Args:
        panels: Panel definitions.
        out_path: Destination HTML path.
        now: CLI reference time, or ``None`` (data-derived).
        title: Page title.
        thumb_width: Thumbnail width.
        thumb_quality: Initial JPEG quality.
        include_frames: Embed thumbnails.
        max_bytes: Hard page-size budget.
        config: Optional rule thresholds.
        lang: Initial language (``en``/``ru``).
        static_growth: Keep the Python-rendered Growth fallback charts.
        max_json_bytes: Hard payload JSON budget.

    Returns:
        The build summary.

    Raises:
        ValueError: For no panels, duplicate ids, a bad language, or a payload
            or page above budget.
        FileNotFoundError: For a missing CSV.
        OSError: If the destination cannot be written.
    """
    if not panels:
        raise ValueError("at least one panel is required")
    ids = [panel.id for panel in panels]
    if len(set(ids)) != len(ids):
        duplicate = next(panel_id for panel_id in ids if ids.count(panel_id) > 1)
        raise ValueError(f"duplicate panel id: {duplicate}")
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    rows_by_panel = {panel.id: load_rows(panel.csv_path) for panel in panels}
    payload = build_payload(panels, now=now, title=title, config=config)
    assets, records = _frame_assets(
        panels,
        rows_by_panel,
        include=include_frames,
        width=thumb_width,
        quality=thumb_quality,
    )
    payload["frames"] = records
    payload["cards"] = cards_for_payload(payload)
    for card in payload["cards"]:
        if str(card.get("id")) in PER_PANEL_CONCLUSION:
            # Full single-panel sentences stay server-side; the client formats
            # the same summary from the compact ``single_values`` block.
            card.pop("conclusion_parts", None)
    known_cards = {str(card["id"]) for card in payload["cards"]}
    for finding in payload["findings"]:
        if finding.get("anchor") not in known_cards:
            finding["anchor"] = ""
    svgs = _svg_for(payload, assets, lang, static_growth=static_growth)
    document = layout.render_page(
        payload, svgs, frames=assets, js=layout.JS, lang=lang
    )
    size = len(document.encode("utf-8"))
    json_bytes = len(
        json.dumps(
            payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
    )
    if json_bytes > max_json_bytes:
        raise ValueError(f"payload {json_bytes} bytes exceeds budget {max_json_bytes}")
    if size > max_bytes:
        raise ValueError(f"output {size} bytes exceeds budget {max_bytes}")
    destination = Path(out_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_bytes(document.encode("utf-8"))
    os.replace(temporary, destination)
    now_utc, _source = resolve_now(rows_by_panel, now)
    findings: list[Finding] = []
    for panel in panels:
        findings.extend(
            evaluate_rules(rows_by_panel[panel.id], now=now_utc, config=config)
        )
    return ReportResult(
        out_path=destination,
        panels=len(panels),
        rows_total=sum(len(rows) for rows in rows_by_panel.values()),
        days=int(payload["totals"]["days"]),  # type: ignore[index]
        findings=tuple(findings),
        charts=len(svgs),
        frames=len(records),
        bytes_total=size,
        json_bytes=json_bytes,
        now_source=str(payload["now_source"]),
    )
