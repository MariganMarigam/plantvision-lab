"""Card, table, evidence and link assembly for the v3 payload.

B1 joins six Crops cards and six Data-quality cards. Every displayed number is
computed here; the client only maps precomputed values to geometry.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone
from typing import Mapping, Sequence

from plantvision.analytics.dashboard import model
from plantvision.analytics.dashboard.charts import (
    BarItem,
    ChartSpec,
    PlotSeries,
    SmallMultiple,
    Threshold,
    bar_chart,
    line_chart,
    ring,
    small_multiples,
)
from plantvision.analytics.dashboard.contract import RENDER
from plantvision.analytics.dashboard.svg import esc, fmt_value, num
from plantvision.analytics.rules import (
    VALIDITY_RULE_ID,
    Finding,
    RuleConfig,
    is_true,
    parse_timestamp,
)
from plantvision.analytics.validity import ValidityTable

from . import derive
from .gate import GatedRow, gate_rows, gate_series, evaluate_gated_rules, resolve_series_state
from .types import Gate2Bundle, GateState, SeriesBlock, ServiceOptions, SourceBundle

_UTC = timezone.utc
_DAY_SECONDS = 86400.0

SERIES_METRICS: dict[str, tuple[str, int]] = {
    "area_px": ("px", 0),
    "area_cm2": ("cm²", 2),
}

RULE_CARDS: dict[str, list[str]] = {
    "growth-stall": ["cd-area-line", "cp-index-line"],
    "area-drop": ["cd-area-line", "cp-daily-bars"],
    "solidity-drop": ["sh-solidity", "sh-radar"],
    "scale-coverage": ["dq-scale-stacked", "dq-scale-ring", "cd-kpi-rings"],
    "capture-gap": ["dq-gap-bars", "ca-calendar"],
    "stale-data": ["cd-kpi-rings", "al-table"],
    "quality-flag-rate": ["dq-quality-bars", "dq-provenance-heatmap"],
    "camera-settings-change": ["dq-provenance-heatmap", "me-provenance-table"],
    "camera-settings-provenance": ["dq-provenance-heatmap", "me-provenance-table"],
    VALIDITY_RULE_ID: ["al-validity", "me-validity-matrix", "cd-area-line"],
}

_TITLES: dict[str, tuple[str, str]] = {
    "cd-identity": ("Plant identity", "Идентичность растения"),
    "cd-kpi-rings": ("Supply health", "Здоровье поставки"),
    "cd-area-line": ("Projected area", "Проекционная площадь"),
    "cd-light-compare": ("Light comparison", "Сравнение света"),
    "cd-frame-thumb": ("Frame check", "Проверка кадра"),
    "cd-coverage-table": ("Column coverage", "Покрытие колонок"),
    "dq-scale-stacked": ("Scale coverage", "Покрытие масштаба"),
    "dq-scale-ring": ("Scale ring", "Кольцо масштаба"),
    "dq-quality-bars": ("Quality flags", "Флаги качества"),
    "dq-gap-bars": ("Capture gaps", "Пропуски съёмки"),
    "dq-provenance-heatmap": ("Provenance heatmap", "Карта провенанса"),
    "dq-coverage-table": ("Coverage table", "Таблица покрытия"),
}

_COPY: dict[str, dict[str, tuple[str, str]]] = {
    "cd-identity": {
        "what": (
            "The camera, zone, experiment and pipeline behind this panel.",
            "Камера, зона, эксперимент и конвейер, стоящие за панелью.",
        ),
        "how": (
            "Blank provenance is shown as not recorded, never as a zero.",
            "Пустой провенанс показан как «не записано», а не как ноль.",
        ),
        "do": (
            "Populate experiment and plant ids before comparing panels.",
            "Заполните идентификаторы эксперимента и растения до сравнения панелей.",
        ),
    },
    "cd-kpi-rings": {
        "what": (
            "Scale coverage, quality-defect share and freshness for this panel.",
            "Покрытие масштаба, доля дефектов качества и свежесть этой панели.",
        ),
        "how": (
            "Each ring is a share of the panel's frames; a missing ring is not measured.",
            "Каждое кольцо — доля кадров панели; отсутствующее кольцо не измерено.",
        ),
        "do": (
            "Fix the lowest ring first and re-check the 45 mm marker.",
            "Сначала исправьте самое низкое кольцо и перепроверьте маркер 45 мм.",
        ),
    },
    "cd-area-line": {
        "what": (
            "Projected canopy area over capture time, split by condition.",
            "Проекционная площадь кроны по времени съёмки, разделённая по условию.",
        ),
        "how": (
            "Gaps break the line; an invalid condition is hatched and locked, never averaged.",
            "Разрывы ломают линию; недопустимое условие штрихуется и блокируется, без усреднения.",
        ),
        "do": (
            "Do not quote an invalid area; open Method › validity for the verdict.",
            "Не цитируйте недопустимую площадь; откройте Метод › валидность.",
        ),
    },
    "cd-light-compare": {
        "what": (
            "Two panels, one per light regime, same plant and method.",
            "Две панели, по одной на световой режим, одно растение и метод.",
        ),
        "how": (
            "Read each panel on its own axis; the rule is the light switch, not a data gap.",
            "Читайте каждую панель по своей оси; линия — переключение света, а не пропуск данных.",
        ),
        "do": (
            "Never average the two sides; fix the method per condition first.",
            "Никогда не усредняйте стороны; сначала исправьте метод для каждого условия.",
        ),
    },
    "cd-frame-thumb": {
        "what": (
            "The first frame behind this panel, for a framing check.",
            "Первый кадр панели для проверки кадрирования.",
        ),
        "how": (
            "Framing is checked, not the plant; a missing file is reported with its path.",
            "Проверяется кадрирование, а не растение; отсутствующий файл показывается с путём.",
        ),
        "do": (
            "Re-align the bracket when the frame no longer matches the reference.",
            "Переставьте кронштейн, если кадр больше не совпадает с эталоном.",
        ),
    },
    "cd-coverage-table": {
        "what": (
            "Which columns this panel actually measured.",
            "Какие колонки эта панель действительно измерила.",
        ),
        "how": (
            "Sorted by coverage ascending so the gaps surface first.",
            "Сортировка по покрытию возрастает, поэтому пропуски видны первыми.",
        ),
        "do": (
            "Treat 0 % as absence of a measurement, not as a healthy zero.",
            "Считайте 0 % отсутствием измерения, а не здоровым нулём.",
        ),
    },
    "dq-scale-stacked": {
        "what": (
            "Measured versus unknown scale rows per panel.",
            "Измеренные и неизвестные строки масштаба по панелям.",
        ),
        "how": (
            "The column height is row count, not a percentage; a short column is a small sample.",
            "Высота столбца — число строк, а не процент; короткий столбец — малая выборка.",
        ),
        "do": (
            "Prefer px area for trend and re-capture the marker where coverage is low.",
            "Для тренда используйте площадь в px и переснимите маркер там, где покрытие низкое.",
        ),
    },
    "dq-scale-ring": {
        "what": (
            "One number for scale coverage across the selected panels.",
            "Одно число покрытия масштаба по выбранным панелям.",
        ),
        "how": (
            "A ring shows a share of frames, not a growth direction.",
            "Кольцо показывает долю кадров, а не направление роста.",
        ),
        "do": (
            "If the ring is low, cm² claims are not comparable.",
            "Если кольцо низкое, заявления в cm² несопоставимы.",
        ),
    },
    "dq-quality-bars": {
        "what": (
            "Quality-defect tokens across the selected panels.",
            "Токены дефектов качества по выбранным панелям.",
        ),
        "how": (
            "A blank quality column means no claim, not a clean frame.",
            "Пустая колонка качества означает отсутствие заявления, а не чистый кадр.",
        ),
        "do": (
            "Check blur, darkness and brightness in the raw frames before trusting a trend.",
            "Проверьте смаз, темноту и пересвет в исходных кадрах до доверия тренду.",
        ),
    },
    "dq-gap-bars": {
        "what": (
            "The largest capture intervals per panel, in hours.",
            "Наибольшие интервалы съёмки по панелям, в часах.",
        ),
        "how": (
            "A five-minute cadence is the baseline; a gap is a supply hole, not a zero.",
            "Базовая частота — пять минут; пропуск — дыра в поставке, а не ноль.",
        ),
        "do": (
            "Match every gap above 12 hours to the capture log.",
            "Сопоставьте каждый пропуск больше 12 часов с журналом съёмки.",
        ),
    },
    "dq-provenance-heatmap": {
        "what": (
            "Share of non-blank cells for every canonical column and panel.",
            "Доля непустых ячеек для каждой канонической колонки и панели.",
        ),
        "how": (
            "0 % is absence, not health; the label names the column.",
            "0 % — отсутствие, а не здоровье; подпись называет колонку.",
        ),
        "do": (
            "Populate the blank provenance columns before any cross-panel claim.",
            "Заполните пустые колонки провенанса до любого межпанельного заявления.",
        ),
    },
    "dq-coverage-table": {
        "what": (
            "Exact non-blank counts per column across the selected panels.",
            "Точные непустые счётчики по колонкам выбранных панелей.",
        ),
        "how": (
            "The denominator is the row count; 0 % is not the same as zero measured.",
            "Знаменатель — число строк; 0 % не равно измеренному нулю.",
        ),
        "do": (
            "Fix the lowest-coverage column that a decision depends on.",
            "Исправьте колонку с наименьшим покрытием, от которой зависит решение.",
        ),
    },
}


def _iso_z(moment: datetime) -> str:
    """ISO-8601 UTC string with trailing ``Z``."""
    return moment.astimezone(_UTC).isoformat().replace("+00:00", "Z")


def _metric_validity(validity: ValidityTable, method_version: str, condition: str, metric: str) -> dict[str, object]:
    """Validity envelope for one metric/condition pair."""
    state = validity.state(method_version, condition, metric)
    record = next(
        (
            item
            for item in validity.records
            if item.method_version == method_version
            and item.condition_key == condition
            and item.metric == metric
        ),
        None,
    )
    return {
        "state": state,
        "method_id": record.method_id if record else "",
        "method_version": method_version,
        "metric": metric,
        "condition_key": condition,
        "evidence_id": record.evidence_id if record else "",
        "badge_en": _badge(state, condition, "en"),
        "badge_ru": _badge(state, condition, "ru"),
    }


def _badge(state: str, condition: str, lang: str) -> str:
    """One-word validity badge."""
    light = ""
    for part in condition.split("|"):
        if part.startswith("light="):
            light = part.split("=", 1)[1]
            break
    if lang == "ru":
        words = {"valid": "допустимо", "invalid": "недопустимо", "unproven": "не доказано"}
    else:
        words = {"valid": "valid", "invalid": "invalid", "unproven": "unproven"}
    word = words.get(state, state)
    return f"{word} for {light}" if light else word


def _panel_payload(
    panel: object,
    raw_rows: Sequence[dict[str, str]],
    gated: Sequence[GatedRow],
    findings: Sequence[Finding],
    now: datetime,
    validity: ValidityTable,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Build one panel block and its metric series map."""
    panel_id = str(getattr(panel, "id", ""))
    condition = gated[0].condition_key if gated else ""
    dated = [
        (parse_timestamp(row.get("captured_at")), row)
        for row in raw_rows
        if parse_timestamp(row.get("captured_at")) is not None
    ]
    dated.sort(key=lambda pair: pair[0])  # type: ignore[arg-type,return-value]
    first_at = _iso_z(dated[0][0]) if dated else ""  # type: ignore[arg-type]
    last_at = _iso_z(dated[-1][0]) if dated else ""  # type: ignore[arg-type]
    span_hours = (
        (dated[-1][0] - dated[0][0]).total_seconds() / 3600.0 if dated else None
    )
    age_days = (
        max(0.0, (now - dated[-1][0]).total_seconds() / _DAY_SECONDS) if dated else None
    )
    dates = sorted({item[0].date().isoformat() for item in dated})  # type: ignore[union-attr]
    camera = next((row.get("camera_id", "").strip() for row in raw_rows if row.get("camera_id", "").strip()), "")
    zone = next((row.get("zone_id", "").strip() for row in raw_rows if row.get("zone_id", "").strip()), "")
    series: dict[str, object] = {}
    for metric, (unit, decimals) in SERIES_METRICS.items():
        state = validity.state(str(getattr(panel, "pipeline_version", "")), condition, metric)
        block = derive.series_block(
            [item.row for item in gated],
            metric,
            unit=unit,
            decimals=decimals,
            condition=condition,
            state="ok",
            validity=_metric_validity(
                validity, str(getattr(panel, "pipeline_version", "")), condition, metric
            ),
        )
        resolved = resolve_series_state(state, block.measured)
        resolved_block = gate_series(block, resolved)
        if resolved is GateState.INVALID:
            original_values = [
                value
                for item in gated
                if (value := derive.finite(item.original, metric)) is not None
            ]
            resolved_block = SeriesBlock(
                unit=resolved_block.unit,
                decimals=resolved_block.decimals,
                measured=len(original_values),
                missing=len(gated) - len(original_values),
                source_points=len(gated),
                downsampled=False,
                runs=(),
                gaps=(),
                stats=derive.stats(original_values),
                condition_key=resolved_block.condition_key,
                series_state=resolved_block.series_state,
                draw=resolved_block.draw,
                validity=resolved_block.validity,
            )
        series[metric] = resolved_block.as_json()
    kpi = model.panel_kpi([item.row for item in gated], now=now)
    quality = model.quality_block([item.row for item in gated])
    verdict = "unknown"
    severities = {finding.severity for finding in findings}
    if "critical" in severities:
        verdict = "critical"
    elif "warn" in severities:
        verdict = "warn"
    elif findings or raw_rows:
        verdict = "ok"
    return (
        {
            "id": panel_id,
            "label": str(getattr(panel, "label", "")),
            "crop": str(getattr(panel, "crop", "")),
            "method": str(getattr(panel, "method", "")),
            "method_label": str(getattr(panel, "method_label", "")),
            "pipeline_version": str(getattr(panel, "pipeline_version", "")),
            "source": str(getattr(panel, "csv_path", "")),
            "note": str(getattr(panel, "note", "")),
            "camera": camera,
            "zone": zone,
            "rows": len(raw_rows),
            "days": len(dates),
            "first_at": first_at,
            "last_at": last_at,
            "span_hours": None if span_hours is None else round(span_hours, 2),
            "age_days": None if age_days is None else round(age_days, 2),
            "verdict": verdict,
            "conditions": [condition] if condition else [],
            "condition_key": condition,
            "light_regime": str(getattr(panel, "light_regime", "")),
            "kpi": kpi,
            "quality": quality,
            "shape": {"radar": [], "range": {}},
        },
        series,
    )


def _measurement_block(panel_id: str, gated: Sequence[GatedRow]) -> dict[str, object]:
    """Row-oriented point → frame lookup with gated numeric cells.

    B1 caps the lookup at 12 evenly spaced frames per panel to keep the
    versioned payload inside its byte budget; first and last are preserved.
    """
    columns = [
        "ts", "area_px", "area_cm2", "solidity", "perimeter_px",
        "scale_ok", "quality_flag", "sha256",
    ]
    prepared: list[list[object]] = []
    for item in gated:
        timestamp = parse_timestamp(item.row.get("captured_at"))
        if timestamp is None:
            continue
        prepared.append(
            [
                int(timestamp.timestamp() * 1000.0),
                derive.finite(item.row, "area_px"),
                derive.finite(item.row, "area_cm2"),
                derive.finite(item.row, "solidity"),
                derive.finite(item.row, "perimeter_px"),
                is_true(item.row.get("scale_ok")),
                (item.row.get("quality_flag") or "").strip(),
                (item.row.get("sha256") or "").strip(),
            ]
        )
    limit = 12
    if len(prepared) > limit:
        indices = sorted(
            {round(index * (len(prepared) - 1) / (limit - 1)) for index in range(limit)}
        )
        prepared = [prepared[index] for index in indices]
    return {"columns": columns, "rows": prepared}


def _coverage_table(panel_id: str, rows: Sequence[dict[str, str]]) -> dict[str, object]:
    """Preformatted coverage table for one panel."""
    blocks = model.coverage_block(rows)
    table_rows: list[dict[str, object]] = []
    for block in sorted(blocks, key=lambda item: (float(item["pct"]), str(item["column"]))):
        state = "ok" if block["measured"] else "not_recorded"
        table_rows.append(
            {
                "cells": {
                    "column": str(block["column"]),
                    "measured": f"{int(block['measured'])}",
                    "total": f"{int(block['total'])}",
                    "pct": f"{float(block['pct']):.1f} %",
                },
                "state": state,
            }
        )
    return {
        "columns": [
            {"key": "column", "label_en": "Column", "label_ru": "Колонка", "align": "left", "format": "text"},
            {"key": "measured", "label_en": "Measured", "label_ru": "Измерено", "align": "right", "format": "int"},
            {"key": "total", "label_en": "Total", "label_ru": "Всего", "align": "right", "format": "int"},
            {"key": "pct", "label_en": "Coverage", "label_ru": "Покрытие", "align": "right", "format": "pct"},
        ],
        "rows": table_rows,
        "empty": "not measured",
        "id": f"coverage.{panel_id}",
    }


def _coverage_html(table: dict[str, object]) -> str:
    """Render a preformatted coverage table as HTML."""
    columns = table.get("columns", [])
    head = "".join(
        f'<th scope="col" class="{esc(str(col.get("align", "left")))}">'
        f'{esc(str(col.get("label_en", "")))}</th>'
        for col in columns  # type: ignore[union-attr]
    )
    body: list[str] = []
    for row in table.get("rows", []):  # type: ignore[union-attr]
        cells = row.get("cells", {})
        state = str(row.get("state", "ok"))
        body.append(
            f'<tr data-state="{esc(state)}">'
            + "".join(
                f'<td class="{esc(str(col.get("align", "left")))}">'
                f'{esc(str(cells.get(col.get("key"), "")))}</td>'
                for col in columns  # type: ignore[union-attr]
            )
            + "</tr>"
        )
    return (
        '<div class="pv-tablewrap pv-g2-table"><table>'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


def _identity_html(panel: Mapping[str, object], rows: Sequence[dict[str, str]]) -> str:
    """Render the identity table with explicit not-recorded chips."""
    first = rows[0] if rows else {}
    fields = [
        ("camera_id", str(panel.get("camera", ""))),
        ("zone_id", str(panel.get("zone", ""))),
        ("experiment_id", (first.get("experiment_id") or "").strip()),
        ("biosource_id", (first.get("biosource_id") or "").strip()),
        ("observation_unit_id", (first.get("observation_unit_id") or "").strip()),
        ("condition_key", str(panel.get("condition_key", ""))),
        ("light_regime", str(panel.get("light_regime", ""))),
        ("pipeline_version", str(panel.get("pipeline_version", ""))),
        ("settings_source", (first.get("settings_source") or "").strip()),
    ]
    body = "".join(
        f"<tr><th scope=\"row\">{esc(label)}</th>"
        f"<td>{esc(value) if value else '<span class=\"pv-chip\" data-state=\"not-recorded\">not recorded</span>'}</td></tr>"
        for label, value in fields
    )
    return (
        '<div class="pv-tablewrap pv-g2-table"><table><tbody>'
        f"{body}</tbody></table></div>"
    )


def _invalid_html(state: str, reason: str) -> str:
    """Hatched and locked chart body with the reason in plain text."""
    glyph = "🔒" if state == "invalid" else "?"
    return (
        f'<div class="pv-g2-invalid" data-state="{esc(state)}">'
        f'<svg class="pv-chart" viewBox="0 0 720 240" role="img" '
        f'aria-label="{esc(reason)}">'
        f'<rect x="44" y="18" width="658" height="182" fill="url(#pv-hatch-a)" opacity="0.45"/>'
        f'<text x="373" y="112" text-anchor="middle" class="pv-lock">{glyph}</text>'
        f'<text x="373" y="136" text-anchor="middle" class="pv-ax">{esc(reason)}</text>'
        "</svg></div>"
    )


def _small_panel(panel: Mapping[str, object], series: Mapping[str, object]) -> SmallMultiple:
    """One light-regime side for the small-multiples chart."""
    block = series.get("area_px", {})
    runs = block.get("runs", []) if isinstance(block, dict) else []
    stats = block.get("stats") or {}
    state = str(block.get("series_state", "empty")) if isinstance(block, dict) else "empty"
    if state == "invalid":
        text = f"invalid · n={int(block.get('measured', 0))}"
    elif stats:
        text = f"n={int(stats.get('n', 0))} · median {fmt_value(float(stats['median']), 0, 'px')}"
    else:
        text = "not measured"
    light = str(panel.get("light_regime", "")) or "condition"
    return SmallMultiple(
        label=f"{light} · {text}",
        runs=runs,
        state=state,
        stat_text=text,
    )


def _stacked_svg(panels: Sequence[Mapping[str, object]]) -> str:
    """Measured vs unknown scale rows per panel (counts, not percentages)."""
    width, height = 720, 240
    left, top, bottom = 44, 18, 202
    plot_h = bottom - top
    gap = 24
    bar_w = min(48, max(18, (width - left - 20 - gap * max(1, len(panels))) // max(1, len(panels))))
    total_max = max((int(panel.get("rows", 0)) for panel in panels), default=0) or 1
    parts = [
        f'<svg class="pv-chart" viewBox="0 0 {width} {height}" role="img" aria-label="Scale coverage">'
    ]
    for index, panel in enumerate(panels):
        rows = int(panel.get("rows", 0))
        kpi = panel.get("kpi") if isinstance(panel.get("kpi"), dict) else {}
        scale_pct = kpi.get("scale_pct")
        measured = int(round(rows * (float(scale_pct) if scale_pct is not None else 0.0) / 100.0))
        unknown = max(0, rows - measured)
        x = left + index * (bar_w + gap)
        h_measured = plot_h * measured / total_max
        h_unknown = plot_h * unknown / total_max
        parts.append(
            f'<rect x="{num(x)}" y="{num(bottom - h_measured)}" width="{bar_w}" '
            f'height="{num(h_measured)}" fill="url(#pv-grad-b)"/>'
        )
        parts.append(
            f'<rect x="{num(x)}" y="{num(bottom - h_measured - h_unknown)}" width="{bar_w}" '
            f'height="{num(h_unknown)}" fill="var(--pv-track)" opacity="0.55"/>'
        )
        parts.append(
            f'<text x="{num(x + bar_w / 2)}" y="{bottom + 14}" text-anchor="middle" '
            f'class="pv-ax">{esc(str(panel.get("id", "")))}</text>'
        )
        parts.append(
            f'<text x="{num(x + bar_w / 2)}" y="{num(max(top + 10, bottom - h_measured - h_unknown - 4))}" '
            f'text-anchor="middle" class="pv-ax">{rows}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _heatmap_svg(panels: Sequence[Mapping[str, object]], coverage: Mapping[str, dict[str, object]]) -> str:
    """Column × panel coverage heatmap with 0 % hatched."""
    columns = sorted(
        {
            str(row["cells"]["column"])
            for table in coverage.values()
            for row in table.get("rows", [])
        }
    )
    width = 720
    cell_w = max(44, (width - 190) // max(1, len(panels)))
    cell_h = 7
    height = 26 + len(columns) * (cell_h + 2)
    parts = [
        f'<svg class="pv-chart" viewBox="0 0 {width} {max(160, height)}" role="img" aria-label="Provenance coverage">'
    ]
    for index, panel in enumerate(panels):
        x = 190 + index * cell_w
        parts.append(
            f'<text x="{num(x + cell_w / 2)}" y="12" text-anchor="middle" class="pv-ax">'
            f'{esc(str(panel.get("id", "")))}</text>'
        )
    for row_index, column in enumerate(columns):
        y = 22 + row_index * (cell_h + 2)
        parts.append(
            f'<text x="184" y="{num(y + 6)}" text-anchor="end" class="pv-ax">'
            f'{esc(column)}</text>'
        )
        for panel_index, panel in enumerate(panels):
            table = coverage.get(str(panel.get("id", "")), {})
            pct = 0.0
            for row in table.get("rows", []):
                if str(row["cells"]["column"]) == column:
                    pct = float(str(row["cells"]["pct"]).rstrip(" %"))
                    break
            x = 190 + panel_index * cell_w
            if pct <= 0:
                fill = "url(#pv-hatch-a)"
                opacity = "0.35"
            else:
                fill = "var(--pv-grad-b)"
                opacity = f"{0.25 + 0.75 * min(1.0, pct / 100.0):.2f}"
            parts.append(
                f'<rect x="{num(x)}" y="{num(y)}" width="{cell_w - 3}" height="{cell_h}" '
                f'rx="2" fill="{fill}" opacity="{opacity}"><title>{esc(column)} · {pct:.1f} %</title></rect>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _aggregate_coverage(panel_rows: Mapping[str, Sequence[dict[str, str]]]) -> list[dict[str, object]]:
    """Coverage per column across every panel, weighted by rows."""
    totals: dict[str, list[int]] = {}
    for rows in panel_rows.values():
        for block in model.coverage_block(rows):
            entry = totals.setdefault(str(block["column"]), [0, 0])
            entry[0] += int(block["measured"])
            entry[1] += int(block["total"])
    result: list[dict[str, object]] = []
    for column in sorted(totals):
        measured, total = totals[column]
        result.append(
            {
                "column": column,
                "measured": measured,
                "total": total,
                "pct": round(100.0 * measured / total, 1) if total else 0.0,
            }
        )
    return result


def _aggregate_coverage_table(panel_rows: Mapping[str, Sequence[dict[str, str]]]) -> dict[str, object]:
    """Preformatted cross-panel coverage table."""
    blocks = _aggregate_coverage(panel_rows)
    rows = [
        {
            "cells": {
                "column": str(block["column"]),
                "measured": str(block["measured"]),
                "total": str(block["total"]),
                "pct": f"{float(block['pct']):.1f} %",
            },
            "state": "ok" if block["measured"] else "not_recorded",
        }
        for block in sorted(blocks, key=lambda item: (float(item["pct"]), str(item["column"])))
    ]
    return {
        "columns": [
            {"key": "column", "label_en": "Column", "label_ru": "Колонка", "align": "left", "format": "text"},
            {"key": "measured", "label_en": "Measured", "label_ru": "Измерено", "align": "right", "format": "int"},
            {"key": "total", "label_en": "Total", "label_ru": "Всего", "align": "right", "format": "int"},
            {"key": "pct", "label_en": "Coverage", "label_ru": "Покрытие", "align": "right", "format": "pct"},
        ],
        "rows": rows,
        "empty": "not measured",
        "id": "coverage.all",
    }


def _card_block(
    card_id: str,
    *,
    tab: str,
    sub: str,
    primitive: str,
    span: int,
    panel_scope: str,
    state: str,
    state_reason: str,
    validity: Mapping[str, object],
    title: tuple[str, str],
    copy: Mapping[str, tuple[str, str]],
    now_en: str = "",
    now_ru: str = "",
    conclusion_en: str = "",
    conclusion_ru: str = "",
    reads: Sequence[str] = (),
    series_keys: Sequence[Sequence[str]] = (),
    table_id: str | None = None,
    evidence: Sequence[str] = (),
    dom_id: str | None = None,
    metric: str = "",
    condition: str = "",
) -> dict[str, object]:
    """Build one layout-compatible card record."""
    slots = {
        f"{slot}_{lang}": texts[0 if lang == "en" else 1]
        for slot, texts in copy.items()
        for lang in ("en", "ru")
    }
    slots.update(
        {
            "now_en": now_en or "not measured",
            "now_ru": now_ru or "не измерено",
            "conclusion_en": conclusion_en or now_en or "not measured",
            "conclusion_ru": conclusion_ru or now_ru or "не измерено",
        }
    )
    return {
        "id": card_id,
        "dom_id": dom_id or card_id,
        "tab": tab,
        "sub": sub,
        "chart": primitive,
        "primitive": primitive,
        "span": span,
        "panel_scope": panel_scope,
        "state": state,
        "state_reason": state_reason,
        "validity": dict(validity),
        "metric": metric,
        "condition_key": condition,
        "reads": list(reads),
        "series_keys": [list(item) for item in series_keys],
        "table_id": table_id,
        "evidence": list(evidence),
        "slots": slots,
        "title_en": title[0],
        "title_ru": title[1],
        **{key: value for key, value in slots.items()},
        "filter": {"crop": "full", "window": "full", "agg": "full", "mode": "full"},
        "filter_scope": "panel" if panel_scope == "panel" else "all-panels",
        "key": "area_px" if card_id == "cd-area-line" else "",
        "render": "static",
        "conclusion": {"en": slots["conclusion_en"], "ru": slots["conclusion_ru"]},
    }


def _light_siblings(
    panel: Mapping[str, object], all_panels: Mapping[str, dict[str, object]]
) -> list[dict[str, object]]:
    """Panels that share one CSV but split by light regime."""
    source = str(panel.get("source", ""))
    if not source:
        return []
    siblings = [
        item
        for item in all_panels.values()
        if str(item.get("source", "")) == source and str(item.get("light_regime", ""))
    ]
    return sorted(siblings, key=lambda item: str(item.get("id", ""))) if len(siblings) > 1 else []


def _metric_block(series: Mapping[str, object], metric: str) -> Mapping[str, object]:
    """Read one metric block from a panel series map."""
    block = series.get(metric, {})
    return block if isinstance(block, Mapping) else {}


def _validity_evidence(validity: ValidityTable, method_version: str, condition: str, metric: str) -> list[str]:
    """Evidence ids for a metric verdict when a record exists."""
    record = next(
        (
            item
            for item in validity.records
            if item.method_version == method_version
            and item.condition_key == condition
            and item.metric == metric
        ),
        None,
    )
    return [record.evidence_id] if record else []


def _crops_cards(
    panel: Mapping[str, object],
    series: Mapping[str, object],
    raw_rows: Sequence[dict[str, str]],
    validity: ValidityTable,
    *,
    dom_prefix: str,
    all_panels: Mapping[str, dict[str, object]],
    series_by_panel: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    """Six Crops cards for one panel sub-tab."""
    panel_id = str(panel["id"])
    condition = str(panel.get("condition_key", ""))
    version = str(panel.get("pipeline_version", ""))
    area_validity = _metric_validity(validity, version, condition, "area_px")
    area_state = str(_metric_block(series, "area_px").get("series_state", "empty"))
    state = {
        "ok": "ok",
        "invalid": "invalid",
        "unproven": "unproven",
        "empty": "empty",
        "not_recorded": "not_recorded",
    }.get(area_state, "empty")
    cards: list[dict[str, object]] = []

    def dom(card_id: str) -> str:
        return f"{card_id}--{panel_id}" if dom_prefix else card_id

    cards.append(
        _card_block(
            "cd-identity",
            tab="crops",
            sub=panel_id,
            primitive="table",
            span=2,
            panel_scope="panel",
            state="ok",
            state_reason="",
            validity=area_validity,
            title=_TITLES["cd-identity"],
            copy=_COPY["cd-identity"],
            now_en=f"camera {panel.get('camera') or 'not recorded'} · zone {panel.get('zone') or 'not recorded'} · condition {condition or 'not recorded'} · pipeline {version or 'not recorded'}.",
            now_ru=f"камера {panel.get('camera') or 'не записано'} · зона {panel.get('zone') or 'не записано'} · условие {condition or 'не записано'} · конвейер {version or 'не записано'}.",
            conclusion_en=f"this panel belongs to {condition or 'an unrecorded condition'} and was produced by {version or 'an unrecorded pipeline'}.",
            conclusion_ru=f"эта панель относится к {condition or 'незаписанному условию'} и получена конвейером {version or 'без версии'}.",
            reads=["panels"],
            evidence=[f"ev:config:{panel_id}", f"ev:csv:{panel_id}"],
            dom_id=dom("cd-identity"),
        )
    )
    kpi = panel.get("kpi") if isinstance(panel.get("kpi"), dict) else {}
    cards.append(
        _card_block(
            "cd-kpi-rings",
            tab="crops",
            sub=panel_id,
            primitive="ring",
            span=2,
            panel_scope="panel",
            state=state if state in {"invalid", "unproven"} else "ok",
            state_reason="validity-violation" if state == "invalid" else ("unproven" if state == "unproven" else ""),
            validity=area_validity,
            title=_TITLES["cd-kpi-rings"],
            copy=_COPY["cd-kpi-rings"],
            now_en=f"scale { _pct(kpi.get('scale_pct')) }; defects { _pct(kpi.get('quality_pct')) }; freshness { _pct(kpi.get('freshness_pct')) }; age {panel.get('age_days') if panel.get('age_days') is not None else 'not measured'} days.",
            now_ru=f"масштаб { _pct(kpi.get('scale_pct')) }; дефекты { _pct(kpi.get('quality_pct')) }; свежесть { _pct(kpi.get('freshness_pct')) }; возраст {panel.get('age_days') if panel.get('age_days') is not None else 'не измерено'} дн.",
            conclusion_en=f"the supply is {state if state != 'ok' else 'healthy'} for {condition or 'this panel'}.",
            conclusion_ru=f"поставка {state if state != 'ok' else 'в норме'} для {condition or 'этой панели'}.",
            reads=["panels"],
            evidence=[f"ev:csv:{panel_id}:scale_ok", f"ev:csv:{panel_id}:captured_at"],
            dom_id=dom("cd-kpi-rings"),
        )
    )
    cards.append(
        _card_block(
            "cd-area-line",
            tab="crops",
            sub=panel_id,
            primitive="line",
            span=2,
            panel_scope="panel",
            state=state,
            state_reason="validity-violation" if state == "invalid" else ("unproven" if state == "unproven" else ""),
            validity=area_validity,
            title=_TITLES["cd-area-line"],
            copy=_COPY["cd-area-line"],
            now_en=f"median {_fmt_block(_metric_block(series, 'area_px'))}; n={int(_metric_block(series, 'area_px').get('measured', 0))}; state {area_state}.",
            now_ru=f"медиана {_fmt_block(_metric_block(series, 'area_px'))}; n={int(_metric_block(series, 'area_px').get('measured', 0))}; состояние {area_state}.",
            conclusion_en=(
                f"under {condition or 'this condition'}, this metric is {area_state}."
                if area_state != "ok"
                else f"the area series is measured for {condition or 'this condition'}."
            ),
            conclusion_ru=(
                f"при {condition or 'этом условии'} метрика {area_state}."
                if area_state != "ok"
                else f"площадь измерена для {condition or 'этого условия'}."
            ),
            reads=[f"series.{panel_id}.area_px", f"measurements.{panel_id}.rows"],
            series_keys=[[panel_id, "area_px"]],
            evidence=[f"ev:csv:{panel_id}:area_px", f"ev:csv:{panel_id}:captured_at"]
            + _validity_evidence(validity, version, condition, "area_px"),
            dom_id=dom("cd-area-line"),
            metric="area_px",
            condition=condition,
        )
    )
    siblings = _light_siblings(panel, all_panels)
    if siblings:
        compare_state = "invalid" if any(
            str(_metric_block(series_by_panel.get(str(item["id"]), {}), "area_px").get("series_state"))
            == "invalid"
            for item in siblings
        ) else "ok"
        parts = " · ".join(
            f"{item.get('light_regime', '')} median "
            f"{_fmt_block(_metric_block(series_by_panel.get(str(item['id']), {}), 'area_px'))}"
            for item in siblings
        )
        compare_evidence = [f"ev:csv:{panel_id}:area_px"]
        for item in siblings:
            compare_evidence.extend(
                _validity_evidence(
                    validity,
                    str(item.get("pipeline_version", "")),
                    str(item.get("condition_key", "")),
                    "area_px",
                )
            )
        cards.append(
            _card_block(
                "cd-light-compare",
                tab="crops",
                sub=panel_id,
                primitive="small-multiples",
                span=3,
                panel_scope="panel",
                state=compare_state,
                state_reason="validity-violation",
                validity=area_validity,
                title=_TITLES["cd-light-compare"],
                copy=_COPY["cd-light-compare"],
                now_en=f"{parts}; each side keeps its own condition.",
                now_ru=f"{parts}; каждая сторона сохраняет своё условие.",
                conclusion_en="the light change, not the plant, explains the step; the sides are never averaged.",
                conclusion_ru="переключение света, а не растение, объясняет скачок; стороны никогда не усредняются.",
                reads=[f"series.{panel_id}.area_px", "conditions"],
                series_keys=[[panel_id, "area_px"]],
                evidence=compare_evidence,
                dom_id=dom("cd-light-compare"),
            )
        )
    first_sha = str(raw_rows[0].get("sha256", "")) if raw_rows else ""
    cards.append(
        _card_block(
            "cd-frame-thumb",
            tab="crops",
            sub=panel_id,
            primitive="image",
            span=1,
            panel_scope="panel",
            state="ok" if first_sha else "not_recorded",
            state_reason="",
            validity=area_validity,
            title=_TITLES["cd-frame-thumb"],
            copy=_COPY["cd-frame-thumb"],
            now_en=f"frame {first_sha[:16] or 'not recorded'} from {panel.get('first_at') or 'an unrecorded time'}.",
            now_ru=f"кадр {first_sha[:16] or 'не записан'} от {panel.get('first_at') or 'незаписанного времени'}.",
            conclusion_en="framing is independent of the validity verdict; the image stays visible.",
            conclusion_ru="кадрирование не зависит от вердикта валидности; изображение остаётся видимым.",
            reads=["panels"],
            evidence=[f"ev:csv:{panel_id}"] + ([f"ev:frame:{first_sha}"] if first_sha else []),
            dom_id=dom("cd-frame-thumb"),
        )
    )
    cards.append(
        _card_block(
            "cd-coverage-table",
            tab="crops",
            sub=panel_id,
            primitive="table",
            span=2,
            panel_scope="panel",
            state="ok",
            state_reason="",
            validity=area_validity,
            title=_TITLES["cd-coverage-table"],
            copy=_COPY["cd-coverage-table"],
            now_en=f"{len(raw_rows)} rows; lowest column coverage {_lowest_coverage(raw_rows)}.",
            now_ru=f"{len(raw_rows)} строк; минимальное покрытие {_lowest_coverage(raw_rows)}.",
            conclusion_en="a blank column is absence, not a zero and not a clean measurement.",
            conclusion_ru="пустая колонка — отсутствие, а не ноль и не чистое измерение.",
            reads=[f"tables.coverage.{panel_id}"],
            table_id=f"coverage.{panel_id}",
            evidence=[f"ev:csv:{panel_id}"],
            dom_id=dom("cd-coverage-table"),
        )
    )
    return cards


def _pct(value: object) -> str:
    """Format an optional percentage."""
    return "not measured" if value is None else f"{float(value):.1f} %"


def _fmt_block(block: Mapping[str, object]) -> str:
    """Format a series block median/last for copy."""
    stats = block.get("stats")
    if not isinstance(stats, dict):
        return "not measured"
    return fmt_value(float(stats["median"]), int(block.get("decimals", 0)), str(block.get("unit", "")))


def _lowest_coverage(rows: Sequence[dict[str, str]]) -> str:
    """Name the least-covered column with its percentage."""
    blocks = model.coverage_block(rows)
    if not blocks:
        return "not measured"
    lowest = min(blocks, key=lambda item: (float(item["pct"]), str(item["column"])))
    return f"{lowest['column']} {float(lowest['pct']):.1f} %"


def _data_quality_cards(
    bundle: SourceBundle,
    panels: Sequence[Mapping[str, object]],
    panel_series: Mapping[str, Mapping[str, object]],
    validity: ValidityTable,
) -> list[dict[str, object]]:
    """Six cross-panel Data-quality cards."""
    cards: list[dict[str, object]] = []
    total_rows = sum(int(panel.get("rows", 0)) for panel in panels)
    total_scale = sum(
        1
        for panel in bundle.panels
        for row in bundle.rows_by_panel.get(str(getattr(panel, "id", "")), [])
        if is_true(row.get("scale_ok"))
    )
    scale_pct = 100.0 * total_scale / total_rows if total_rows else None
    panel_rows = {
        str(getattr(panel, "id", "")): bundle.rows_by_panel.get(str(getattr(panel, "id", "")), [])
        for panel in bundle.panels
    }
    coverage = {
        panel_id: _coverage_table(panel_id, rows) for panel_id, rows in panel_rows.items()
    }
    token_totals = {"ok": 0, "blur": 0, "dark": 0, "bright": 0}
    for rows in panel_rows.values():
        block = model.quality_block(rows)
        for token, count in block.get("tokens", {}).items():
            token_totals[token] = token_totals.get(token, 0) + int(count)
    quality_measured = any(
        (row.get("quality_flag") or "").strip() for rows in panel_rows.values() for row in rows
    )
    cards.append(
        _card_block(
            "dq-scale-stacked",
            tab="data-quality",
            sub="scale",
            primitive="stacked",
            span=2,
            panel_scope="all-panels",
            state="ok",
            state_reason="",
            validity={},
            title=_TITLES["dq-scale-stacked"],
            copy=_COPY["dq-scale-stacked"],
            now_en=f"{total_scale} of {total_rows} rows carry a valid scale across {len(panels)} panels.",
            now_ru=f"{total_scale} из {total_rows} строк имеют валидный масштаб по {len(panels)} панелям.",
            conclusion_en=f"scale coverage is {_pct(scale_pct)}; the worst panel sets the cm² limit.",
            conclusion_ru=f"покрытие масштаба {_pct(scale_pct)}; худшая панель задаёт предел cm².",
            reads=["panels"],
            evidence=[f"ev:csv:{str(panel.get('id'))}:scale_ok" for panel in panels],
            dom_id="dq-scale-stacked",
        )
    )
    cards.append(
        _card_block(
            "dq-scale-ring",
            tab="data-quality",
            sub="scale",
            primitive="ring",
            span=1,
            panel_scope="all-panels",
            state="ok" if scale_pct is not None else "empty",
            state_reason="",
            validity={},
            title=_TITLES["dq-scale-ring"],
            copy=_COPY["dq-scale-ring"],
            now_en=f"{_pct(scale_pct)} of {total_rows} rows have a valid scale.",
            now_ru=f"{_pct(scale_pct)} из {total_rows} строк имеют валидный масштаб.",
            conclusion_en="a low ring means cm² claims are not comparable; px area still works.",
            conclusion_ru="низкое кольцо означает несопоставимость cm²; площадь в px всё ещё работает.",
            reads=["panels"],
            evidence=[f"ev:csv:{str(panel.get('id'))}:scale_ok" for panel in panels],
            dom_id="dq-scale-ring",
        )
    )
    quality_items = [
        BarItem(label=token, value=float(token_totals.get(token, 0)))
        for token in ("ok", "blur", "dark", "bright")
    ]
    cards.append(
        _card_block(
            "dq-quality-bars",
            tab="data-quality",
            sub="quality-flags",
            primitive="bars",
            span=2,
            panel_scope="all-panels",
            state="ok" if quality_measured else "empty",
            state_reason="",
            validity={},
            title=_TITLES["dq-quality-bars"],
            copy=_COPY["dq-quality-bars"],
            now_en=(
                f"ok {token_totals.get('ok', 0)}; blur {token_totals.get('blur', 0)}; "
                f"dark {token_totals.get('dark', 0)}; bright {token_totals.get('bright', 0)}."
                if quality_measured
                else "quality_flag is never recorded in these stores; this is not a clean result."
            ),
            now_ru=(
                f"ok {token_totals.get('ok', 0)}; blur {token_totals.get('blur', 0)}; "
                f"dark {token_totals.get('dark', 0)}; bright {token_totals.get('bright', 0)}."
                if quality_measured
                else "quality_flag нигде не записан; это не означает чистый результат."
            ),
            conclusion_en="a blank quality column is no claim, not a clean frame.",
            conclusion_ru="пустая колонка качества — отсутствие заявления, а не чистый кадр.",
            reads=["panels"],
            evidence=[f"ev:csv:{str(panel.get('id'))}:quality_flag" for panel in panels],
            dom_id="dq-quality-bars",
        )
    )
    gap_items: list[BarItem] = []
    max_gap = 0.0
    for panel in panels:
        panel_id = str(panel.get("id", ""))
        gaps = derive.gap_hours(panel_rows[panel_id])
        if gaps:
            max_gap = max(max_gap, max(gaps))
            gap_items.append(BarItem(label=panel_id, value=max(gaps)))
    cards.append(
        _card_block(
            "dq-gap-bars",
            tab="data-quality",
            sub="gaps",
            primitive="bars",
            span=2,
            panel_scope="all-panels",
            state="ok" if gap_items else "empty",
            state_reason="",
            validity={},
            title=_TITLES["dq-gap-bars"],
            copy=_COPY["dq-gap-bars"],
            now_en=f"largest gap {max_gap:.2f} h across {len(gap_items)} panels; five minutes is the baseline.",
            now_ru=f"наибольший пропуск {max_gap:.2f} ч по {len(gap_items)} панелям; базовая частота — пять минут.",
            conclusion_en="read holes before trusting a daily median.",
            conclusion_ru="сначала читайте дыры, потом доверяйте суточной медиане.",
            reads=["panels"],
            evidence=[f"ev:csv:{str(panel.get('id'))}:captured_at" for panel in panels],
            dom_id="dq-gap-bars",
        )
    )
    cards.append(
        _card_block(
            "dq-provenance-heatmap",
            tab="data-quality",
            sub="provenance",
            primitive="strips",
            span=3,
            panel_scope="all-panels",
            state="ok",
            state_reason="",
            validity={},
            title=_TITLES["dq-provenance-heatmap"],
            copy=_COPY["dq-provenance-heatmap"],
            now_en=f"{len(coverage)} panels × {len({row['cells']['column'] for table in coverage.values() for row in table['rows']})} canonical columns.",
            now_ru=f"{len(coverage)} панелей × {len({row['cells']['column'] for table in coverage.values() for row in table['rows']})} канонических колонок.",
            conclusion_en="0 % is absence, not health; populate provenance before cross-panel claims.",
            conclusion_ru="0 % — отсутствие, а не здоровье; заполните провенанс до межпанельных заявлений.",
            reads=["panels"],
            evidence=[f"ev:csv:{str(panel.get('id'))}" for panel in panels],
            dom_id="dq-provenance-heatmap",
        )
    )
    cards.append(
        _card_block(
            "dq-coverage-table",
            tab="data-quality",
            sub="scale",
            primitive="table",
            span=3,
            panel_scope="all-panels",
            state="ok",
            state_reason="",
            validity={},
            title=_TITLES["dq-coverage-table"],
            copy=_COPY["dq-coverage-table"],
            now_en=f"{total_rows} rows across {len(panels)} panels; exact counts per column.",
            now_ru=f"{total_rows} строк по {len(panels)} панелям; точные счётчики по колонкам.",
            conclusion_en="the denominator is rows, so 0 % is not a measured zero.",
            conclusion_ru="знаменатель — строки, поэтому 0 % не является измеренным нулём.",
            reads=["panels"],
            table_id="coverage.all",
            evidence=[f"ev:csv:{str(panel.get('id'))}" for panel in panels],
            dom_id="dq-coverage-table",
        )
    )
    return cards


def _findings_payload(
    findings: Sequence[tuple[str, Finding]],
    panels: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Flatten gated findings with evidence, cards and span."""
    labels = {str(panel["id"]): str(panel.get("label", "")) for panel in panels}
    entries: list[dict[str, object]] = []
    for panel_id, finding in findings:
        cards = RULE_CARDS.get(finding.rule_id, [])
        span = (
            {"start": finding.window_start, "end": finding.window_end}
            if finding.window_start or finding.window_end
            else None
        )
        evidence_id = (
            f"ev:csv:{panel_id}"
            if finding.rule_id != VALIDITY_RULE_ID
            else f"ev:csv:{panel_id}"
        )
        entries.append(
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
                "anchor": cards[0] if cards else "",
                "evidence_id": evidence_id,
                "cards": list(cards),
                "span": span,
                "rule_version": "rules/1",
            }
        )
    entries.sort(
        key=lambda item: (
            0 if item["severity"] == "critical" else 1,
            str(item["panel"]),
            str(item["rule_id"]),
            str(item["window_start"]),
        )
    )
    return entries


def build_gate2(
    bundle: SourceBundle,
    *,
    now: datetime,
    options: ServiceOptions,
    config: RuleConfig | None,
    conditions: Mapping[str, object],
    validity: Mapping[str, object],
) -> dict[str, object]:
    """Assemble derived v3 sections and the B1 card set.

    Args:
        bundle: Parsed sources.
        now: Resolved UTC reference time.
        options: Build options.
        config: Optional rule thresholds.
        conditions: Pre-built condition section.
        validity: Pre-built validity section.

    Returns:
        A dict with sections, cards, svgs and findings.
    """
    table = bundle.validity
    panels: list[dict[str, object]] = []
    panel_series: dict[str, dict[str, object]] = {}
    measurements: dict[str, object] = {}
    findings_pairs: list[tuple[str, Finding]] = []
    tables: dict[str, object] = {}
    gated_by_panel: dict[str, list[GatedRow]] = {}
    for panel in bundle.panels:
        panel_id = str(getattr(panel, "id", ""))
        raw_rows = bundle.rows_by_panel.get(panel_id, [])
        gated = gate_rows(
            raw_rows,
            table,
            method_version=str(getattr(panel, "pipeline_version", "")),
            panel=panel,
        )
        gated_by_panel[panel_id] = gated
        findings = evaluate_gated_rules(
            gated,
            now,
            config,
            validity=table,
            method_version=str(getattr(panel, "pipeline_version", "")),
            zone=(raw_rows[0].get("zone_id", "").strip() if raw_rows else "unknown"),
        )
        findings_pairs.extend((panel_id, finding) for finding in findings)
        block, series = _panel_payload(panel, raw_rows, gated, findings, now, table)
        panels.append(block)
        panel_series[panel_id] = series
        measurements[panel_id] = _measurement_block(panel_id, gated)
        tables[f"coverage.{panel_id}"] = _coverage_table(panel_id, raw_rows)

    cards: list[dict[str, object]] = []
    all_panels = {str(panel["id"]): panel for panel in panels}
    for index, panel in enumerate(panels):
        panel_id = str(panel["id"])
        cards.extend(
            _crops_cards(
                panel,
                panel_series[panel_id],
                bundle.rows_by_panel.get(panel_id, []),
                table,
                dom_prefix=index > 0,
                all_panels=all_panels,
                series_by_panel=panel_series,
            )
        )
    cards.extend(_data_quality_cards(bundle, panels, panel_series, table))
    tables["coverage.all"] = _aggregate_coverage_table(bundle.rows_by_panel)
    findings = _findings_payload(findings_pairs, panels)

    # Evidence resolution for every referenced id.
    evidence: dict[str, object] = {}
    for panel in panels:
        panel_id = str(panel["id"])
        rows = len(bundle.rows_by_panel.get(panel_id, []))
        evidence[f"ev:csv:{panel_id}"] = {
            "kind": "csv",
            "path": str(panel.get("source", "")),
            "selector": "",
            "rows": rows,
            "validity_row": None,
            "frame_sha": None,
        }
        for metric in ("area_px", "area_cm2", "solidity", "scale_ok", "quality_flag", "captured_at"):
            evidence[f"ev:csv:{panel_id}:{metric}"] = {
                "kind": "csv",
                "path": str(panel.get("source", "")),
                "selector": metric,
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
        raw_rows = bundle.rows_by_panel.get(panel_id, [])
        sha = str(raw_rows[0].get("sha256", "")) if raw_rows else ""
        if sha:
            evidence[f"ev:frame:{sha}"] = {
                "kind": "frame",
                "path": f"data/originals/{panel.get('camera', '')}",
                "selector": sha,
                "rows": None,
                "validity_row": None,
                "frame_sha": sha,
            }
    for record in table.records:
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

    svgs: dict[str, str] = {}
    for card in cards:
        dom_id = str(card["dom_id"])
        card_id = str(card["id"])
        if card_id == "cd-identity":
            panel = all_panels[str(card["sub"])]
            svgs[dom_id] = _identity_html(panel, bundle.rows_by_panel.get(str(panel["id"]), []))
        elif card_id == "cd-kpi-rings":
            panel = all_panels[str(card["sub"])]
            kpi = panel.get("kpi") if isinstance(panel.get("kpi"), dict) else {}
            pieces = []
            for metric, label in (
                ("scale_pct", "Scale"),
                ("quality_pct", "Defects"),
                ("freshness_pct", "Freshness"),
            ):
                value = kpi.get(metric)
                pieces.append(
                    ring(
                        None if value is None else float(value),
                        label=label,
                        chart_id=f"{dom_id}-{metric}",
                    )
                )
            svgs[dom_id] = '<div class="pv-ringrow">' + "".join(pieces) + "</div>"
        elif card_id == "cd-area-line":
            panel_id = str(card["sub"])
            block = _metric_block(panel_series[panel_id], "area_px")
            state = str(block.get("series_state", "empty"))
            if state == "invalid":
                svgs[dom_id] = _invalid_html(
                    "invalid",
                    f"invalid for {card['condition_key']} — open Method › validity",
                )
            elif block.get("runs"):
                spec = ChartSpec(
                    dom_id,
                    str(card["title_en"]),
                    str(card["now_en"]),
                    unit=str(block.get("unit", "px")),
                    decimals=int(block.get("decimals", 0)),
                )
                stats = block.get("stats") or {}
                thresholds = (
                    (Threshold(float(stats["median"]), f"{float(stats['median']):,.0f}", "warn"),)
                    if stats
                    else ()
                )
                svgs[dom_id] = line_chart(
                    spec,
                    [PlotSeries("A", block.get("runs", []), label=str(all_panels[panel_id].get("label", "")))],
                    thresholds=thresholds,
                    width=720,
                    height=240,
                )
            else:
                svgs[dom_id] = _invalid_html("empty", "not measured — no numeric area_px")
        elif card_id == "cd-light-compare":
            switch_raw = conditions.get("switch_at")
            switch_at = None
            if isinstance(switch_raw, str) and switch_raw:
                try:
                    switch_at = int(
                        datetime.fromisoformat(switch_raw.replace("Z", "+00:00")).timestamp() * 1000
                    )
                except ValueError:
                    switch_at = None
            sides = [
                _small_panel(item, panel_series.get(str(item["id"]), {}))
                for item in _light_siblings(all_panels[panel_id], all_panels)
            ]
            spec = ChartSpec(
                dom_id,
                str(card["title_en"]),
                str(card["now_en"]),
                unit="px",
                decimals=0,
            )
            svgs[dom_id] = small_multiples(spec, sides, switch_at=switch_at)
        elif card_id == "cd-frame-thumb":
            panel_id = str(card["sub"])
            rows = bundle.rows_by_panel.get(panel_id, [])
            sha = str(rows[0].get("sha256", "")) if rows else ""
            svgs[dom_id] = (
                '<div class="pv-g2-note"><p class="pv-ax">frame sha256</p>'
                f'<p class="pv-csv">{esc(sha[:24] + "…" if sha else "not recorded")}</p>'
                f'<p class="pv-ax">data/originals/{esc(str(all_panels[panel_id].get("camera", "")))}</p></div>'
            )
        elif card_id == "cd-coverage-table":
            panel_id = str(card["sub"])
            svgs[dom_id] = _coverage_html(tables[f"coverage.{panel_id}"])
        elif card_id == "dq-scale-stacked":
            svgs[dom_id] = _stacked_svg(panels)
        elif card_id == "dq-scale-ring":
            total_rows = sum(int(panel.get("rows", 0)) for panel in panels)
            measured = sum(
                1
                for rows in bundle.rows_by_panel.values()
                for row in rows
                if is_true(row.get("scale_ok"))
            )
            value = 100.0 * measured / total_rows if total_rows else None
            svgs[dom_id] = ring(value, label="Scale", chart_id=dom_id, size=132)
        elif card_id == "dq-quality-bars":
            token_totals = {"ok": 0, "blur": 0, "dark": 0, "bright": 0}
            for rows in bundle.rows_by_panel.values():
                block = model.quality_block(rows)
                for token, count in block.get("tokens", {}).items():
                    token_totals[token] = token_totals.get(token, 0) + int(count)
            items = [BarItem(label=token, value=float(token_totals.get(token, 0))) for token in ("ok", "blur", "dark", "bright")]
            svgs[dom_id] = bar_chart(
                ChartSpec(dom_id, str(card["title_en"]), str(card["now_en"]), unit="frames", decimals=0),
                items,
            )
        elif card_id == "dq-gap-bars":
            items: list[BarItem] = []
            for panel in panels:
                gaps = derive.gap_hours(bundle.rows_by_panel.get(str(panel["id"]), []))
                if gaps:
                    items.append(BarItem(label=str(panel["id"]), value=max(gaps)))
            svgs[dom_id] = bar_chart(
                ChartSpec(dom_id, str(card["title_en"]), str(card["now_en"]), unit="h", decimals=2),
                items,
            )
        elif card_id == "dq-provenance-heatmap":
            coverage = {panel_id: _coverage_table(panel_id, rows) for panel_id, rows in bundle.rows_by_panel.items()}
            svgs[dom_id] = _heatmap_svg(panels, coverage)
        elif card_id == "dq-coverage-table":
            svgs[dom_id] = _coverage_html(_aggregate_coverage_table(bundle.rows_by_panel))

    links = {
        "cards": {
            str(card["id"]): {
                "tab": str(card["tab"]),
                "sub": str(card["sub"]),
                "metric": str(card.get("metric", "")),
                "evidence": list(card.get("evidence", [])),
                "rules": [rule for rule, card_ids in RULE_CARDS.items() if card["id"] in card_ids],
                "drawer": "card",
            }
            for card in cards
        },
        "rules": {
            rule: {
                "cards": card_ids,
                "severity": "critical" if rule == VALIDITY_RULE_ID else "warn",
                "action_en": "Do not quote this metric; open Method › validity."
                if rule == VALIDITY_RULE_ID
                else "Open the linked card.",
                "action_ru": "Не цитируйте эту метрику; откройте Метод › валидность."
                if rule == VALIDITY_RULE_ID
                else "Откройте связанную карточку.",
            }
            for rule, card_ids in RULE_CARDS.items()
        },
        "aliases": {
            "ch-gr-area-px": "cd-area-line",
            "ch-dq-scale-stacked": "dq-scale-stacked",
            "ch-dq-scale-ring": "dq-scale-ring",
            "ch-dq-quality-bars": "dq-quality-bars",
            "ch-dq-gap-bars": "dq-gap-bars",
            "ch-dq-provenance-heatmap": "dq-provenance-heatmap",
            "ch-ov-kpi-rings": "cd-kpi-rings",
        },
    }
    return {
        "panels": panels,
        "series": panel_series,
        "measurements": measurements,
        "tables": tables,
        "cards": cards,
        "links": links,
        "findings": findings,
        "svgs": svgs,
    }
