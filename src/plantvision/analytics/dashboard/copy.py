"""Card registry, bilingual copy (en/ru), field dictionary and actions.

Text is data: :data:`TEXTS` holds every user-visible string under one key per
language, so a key-set difference is a test failure and a missing translation
cannot silently fall back to English. Card ``now`` and ``conclusion`` entries
are format templates filled from the payload at render time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from plantvision.analytics.rules import RuleConfig

__all__ = [
    "ACTIONS",
    "CARDS",
    "CARD",
    "CHIPS",
    "FIELD_DICTIONARY",
    "MISSING_LABELS",
    "TEXTS",
    "cards_for_payload",
    "conclusion",
]

_UI_EN: dict[str, str] = {
    "ui.skip": "Skip to content",
    "ui.open": "Open detail: {title}",
    "ui.close": "Close detail",
    "ui.lang": "RU",
    "ui.asof": "as of {now}",
    "ui.generated": "generated {ts}",
    "ui.verdict": "verdict",
    "ui.coming.title": "Coming in gate 2",
    "ui.coming.body": (
        "This tab is part of the shared shell; its cards ship in gate 2."
    ),
    "ui.empty.notmeasured": "Not measured",
    "ui.empty.notmeasured.body": "This store never recorded this metric.",
    "ui.explain.what": "What this shows",
    "ui.explain.how": "How to read it",
    "ui.explain.now": "Current reading",
    "ui.explain.do": "What to do",
    "ui.explain.plain": "Plain-language reading",
    "ui.thr.caption": "Thresholds: {list}",
    "ui.conclusion.single": (
        "{panel} changed {delta} over {span} of capture, from {first} to "
        "{last} {unit}."
    ),
    "ui.drawer.axes": "Axes",
    "ui.drawer.thresholds": "Thresholds",
    "ui.drawer.stats": "Stats",
    "ui.drawer.source": "Source",
    "ui.axes.x": "X axis",
    "ui.axes.y": "Y axis",
    "ui.axes.step": "Tick step",
    "ui.stats.panels": "panels",
    "ui.stats.frames": "frames",
    "ui.stats.days": "days",
    "ui.stats.measured": "measured",
    "ui.stats.missing": "missing",
    "ui.stats.median": "median",
    "ui.stats.first": "first",
    "ui.stats.last": "last",
    "ui.stats.min": "min",
    "ui.stats.max": "max",
    "ui.ring.scale": "Scale",
    "ui.ring.freshness": "Freshness",
    "ui.ring.pressure": "Alert pressure",
    "ui.ring.shape": "Shape coverage",
    "ui.chip.critical": "critical",
    "ui.chip.warn": "warn",
    "ui.chip.ok": "ok",
    "ui.chip.not-measured": "not measured",
    "ui.chip.not-recorded": "not recorded",
    "ui.chip.not-computable": "not computable",
    "ui.chip.unknown": "unknown",
    "ui.tab.overview": "Overview",
    "ui.tab.crops": "Crops",
    "ui.tab.growth": "Growth",
    "ui.tab.shape": "Shape",
    "ui.tab.data-quality": "Data quality",
    "ui.tab.alerts": "Alerts",
    "ui.tab.compare": "Compare",
    "ui.tab.capture": "Capture",
    "ui.tab.method": "Method",
    "ui.rail.overview": "Overview",
    "ui.rail.crops": "Crops",
    "ui.rail.growth": "Growth",
    "ui.rail.shape": "Shape",
    "ui.rail.data-quality": "Quality",
    "ui.rail.alerts": "Alerts",
    "ui.rail.compare": "Compare",
    "ui.rail.capture": "Capture",
    "ui.rail.method": "Method",
    "ui.sub.overview.status": "status",
    "ui.sub.overview.kpi": "kpi",
    "ui.sub.growth.area-px": "area px",
    "ui.sub.growth.area-cm2": "area cm²",
    "ui.sub.growth.rate": "rate",
    "ui.sub.growth.daily": "daily",
    "ui.table.caption": "Table",
    "ui.footer": (
        "Deterministic rules over the CSV; thresholds in docs/DASHBOARD.md. "
        "No LLM, no database."
    ),
    "ui.controls.crop": "crop",
    "ui.controls.cropAll": "all crops",
    "ui.controls.cropHint": "Select at least one crop",
    "ui.controls.keepOne": "Keep at least one crop selected",
    "ui.controls.window": "window",
    "ui.controls.w24": "24 h",
    "ui.controls.w7": "7 days",
    "ui.controls.w30": "30 days",
    "ui.controls.wAll": "all",
    "ui.controls.agg": "aggregation",
    "ui.controls.raw": "raw",
    "ui.controls.hourly": "hourly",
    "ui.controls.daily": "daily",
    "ui.controls.mode": "mode",
    "ui.controls.abs": "absolute",
    "ui.controls.idx": "index (100)",
    "ui.controls.delta": "delta %",
    "ui.controls.reset": "reset",
    "ui.controls.snapshot": "snapshot",
    "ui.controls.naNoTime": "No time-series cards on this tab",
    "ui.controls.naBarsOnly": "Bars only: mode does not apply",
    "ui.filter.aggregate": "aggregate of all panels",
    "ui.filter.emptyScope": "no panel selected",
    "ui.filter.emptyWindow": "no frames in this window",
    "ui.filter.invalid": "invalid filter: {token}",
    "ui.filter.keepOne": "The last crop cannot be unchecked",
    "ui.filter.hideNote": "Hidden panels leave the axis unchanged",
    "ui.filter.capped": "showing 3 of {n} panels",
    "ui.filter.noFrames": "no frames in {window}",
    "ui.do.ok": (
        "All selected panels are healthy; keep the current capture cadence and "
        "thresholds."
    ),
    "ui.fresh.fresh": "fresh",
    "ui.fresh.warn": "aging",
    "ui.fresh.stale": "stale",
    "ui.fresh.label": "age of the last frame",
    "ui.snap.title": "Snapshot",
    "ui.snap.export": "Export",
    "ui.snap.diff": "Diff",
    "ui.snap.download": "Download JSON",
    "ui.snap.copy": "Copy JSON",
    "ui.snap.badSchema": "Not a pv-snapshot/1 file",
    "ui.snap.filtersDiffer": "Filters differ between A and B",
    "ui.snap.onlyA": "only in A",
    "ui.snap.onlyB": "only in B",
    "ui.snap.unchanged": "unchanged",
    "ui.snap.notComputable": "not computable",
    "ui.snap.waiting": "Choose two snapshot files to compare",
    "ui.snap.empty": "No metrics to compare",
    "ui.snap.path": "path",
    "ui.snap.delta": "Δ",
    "ui.snap.saved": "Snapshot ready",
    "ui.ov.lastchange": "Change since last frame",
    "ui.ov.thumbs": "Last frames",
}

_UI_RU: dict[str, str] = {
    "ui.skip": "Перейти к содержимому",
    "ui.open": "Открыть подробности: {title}",
    "ui.close": "Закрыть подробности",
    "ui.lang": "EN",
    "ui.asof": "на {now}",
    "ui.generated": "собрано {ts}",
    "ui.verdict": "вердикт",
    "ui.coming.title": "Появится на этапе 2",
    "ui.coming.body": (
        "Этот раздел уже есть в общей оболочке; его карточки выйдут на этапе 2."
    ),
    "ui.empty.notmeasured": "Не измерено",
    "ui.empty.notmeasured.body": "Этот архив никогда не записывал эту метрику.",
    "ui.explain.what": "Что показано",
    "ui.explain.how": "Как читать",
    "ui.explain.now": "Текущее значение",
    "ui.explain.do": "Что делать",
    "ui.explain.plain": "Простое объяснение",
    "ui.thr.caption": "Пороги: {list}",
    "ui.conclusion.single": (
        "{panel}: значение изменилось на {delta} за {span} съёмки — с {first} "
        "до {last} {unit}."
    ),
    "ui.drawer.axes": "Оси",
    "ui.drawer.thresholds": "Пороги",
    "ui.drawer.stats": "Статистика",
    "ui.drawer.source": "Источник",
    "ui.axes.x": "Ось X",
    "ui.axes.y": "Ось Y",
    "ui.axes.step": "Шаг делений",
    "ui.stats.panels": "панели",
    "ui.stats.frames": "кадры",
    "ui.stats.days": "дни",
    "ui.stats.measured": "измерено",
    "ui.stats.missing": "пропущено",
    "ui.stats.median": "медиана",
    "ui.stats.first": "первое",
    "ui.stats.last": "последнее",
    "ui.stats.min": "минимум",
    "ui.stats.max": "максимум",
    "ui.ring.scale": "Масштаб",
    "ui.ring.freshness": "Свежесть",
    "ui.ring.pressure": "Давление тревог",
    "ui.ring.shape": "Покрытие формы",
    "ui.chip.critical": "критично",
    "ui.chip.warn": "предупреждение",
    "ui.chip.ok": "норма",
    "ui.chip.not-measured": "не измерено",
    "ui.chip.not-recorded": "не записано",
    "ui.chip.not-computable": "не вычислимо",
    "ui.chip.unknown": "неизвестно",
    "ui.tab.overview": "Обзор",
    "ui.tab.crops": "Культуры",
    "ui.tab.growth": "Рост",
    "ui.tab.shape": "Форма",
    "ui.tab.data-quality": "Качество данных",
    "ui.tab.alerts": "Тревоги",
    "ui.tab.compare": "Сравнение",
    "ui.tab.capture": "Съёмка",
    "ui.tab.method": "Метод",
    "ui.rail.overview": "Обзор",
    "ui.rail.crops": "Культуры",
    "ui.rail.growth": "Рост",
    "ui.rail.shape": "Форма",
    "ui.rail.data-quality": "Качество",
    "ui.rail.alerts": "Алерты",
    "ui.rail.compare": "Сравнение",
    "ui.rail.capture": "Съёмка",
    "ui.rail.method": "Метод",
    "ui.sub.overview.status": "статус",
    "ui.sub.overview.kpi": "показатели",
    "ui.sub.growth.area-px": "площадь px",
    "ui.sub.growth.area-cm2": "площадь см²",
    "ui.sub.growth.rate": "темп",
    "ui.sub.growth.daily": "по дням",
    "ui.table.caption": "Таблица",
    "ui.footer": (
        "Детерминированные правила по CSV; пороги в docs/DASHBOARD.md. "
        "Без LLM и без базы данных."
    ),
    "ui.controls.crop": "культура",
    "ui.controls.cropAll": "все культуры",
    "ui.controls.cropHint": "Выберите хотя бы одну культуру",
    "ui.controls.keepOne": "Оставьте хотя бы одну культуру",
    "ui.controls.window": "окно",
    "ui.controls.w24": "24 ч",
    "ui.controls.w7": "7 дней",
    "ui.controls.w30": "30 дней",
    "ui.controls.wAll": "всё",
    "ui.controls.agg": "агрегация",
    "ui.controls.raw": "по кадрам",
    "ui.controls.hourly": "по часам",
    "ui.controls.daily": "по дням",
    "ui.controls.mode": "режим",
    "ui.controls.abs": "абсолютный",
    "ui.controls.idx": "индекс (100)",
    "ui.controls.delta": "дельта %",
    "ui.controls.reset": "сброс",
    "ui.controls.snapshot": "снимок",
    "ui.controls.naNoTime": "На этой вкладке нет временных рядов",
    "ui.controls.naBarsOnly": "Только столбцы: режим не применяется",
    "ui.filter.aggregate": "агрегат по всем панелям",
    "ui.filter.emptyScope": "не выбрано ни одной панели",
    "ui.filter.emptyWindow": "в этом окне нет кадров",
    "ui.filter.invalid": "неверный фильтр: {token}",
    "ui.filter.keepOne": "Последнюю культуру нельзя снять",
    "ui.filter.hideNote": "Скрытые панели не меняют ось",
    "ui.filter.capped": "показаны 3 из {n} панелей",
    "ui.filter.noFrames": "нет кадров в окне {window}",
    "ui.do.ok": (
        "Все выбранные панели в норме; сохраняйте текущий темп съёмки и пороги."
    ),
    "ui.fresh.fresh": "свежо",
    "ui.fresh.warn": "стареет",
    "ui.fresh.stale": "устарело",
    "ui.fresh.label": "возраст последнего кадра",
    "ui.snap.title": "Снимок",
    "ui.snap.export": "Экспорт",
    "ui.snap.diff": "Сравнение",
    "ui.snap.download": "Скачать JSON",
    "ui.snap.copy": "Копировать JSON",
    "ui.snap.badSchema": "Это не файл pv-snapshot/1",
    "ui.snap.filtersDiffer": "Фильтры в A и B различаются",
    "ui.snap.onlyA": "только в A",
    "ui.snap.onlyB": "только в B",
    "ui.snap.unchanged": "без изменений",
    "ui.snap.notComputable": "не вычислимо",
    "ui.snap.waiting": "Выберите два файла снимков для сравнения",
    "ui.snap.empty": "Нет метрик для сравнения",
    "ui.snap.path": "путь",
    "ui.snap.delta": "Δ",
    "ui.snap.saved": "Снимок готов",
    "ui.ov.lastchange": "Изменение с последнего кадра",
    "ui.ov.thumbs": "Последние кадры",
}

FILTER_SCOPE: dict[str, tuple[str, str, str, str]] = {
    "ch-gr-area-px": ("full", "full", "full", "full"),
    "ch-gr-area-cm2": ("full", "full", "full", "full"),
    "ch-gr-rate-bars": ("full", "full", "full", "n/a"),
    "ch-gr-daily-bars": ("full", "full", "n/a", "n/a"),
    "ch-gr-daily-table": ("full", "full", "n/a", "n/a"),
    "ch-ov-kpi-rings": ("all-panels", "n/a", "n/a", "n/a"),
    "ch-ov-frames-bars": ("hide", "full", "n/a", "n/a"),
    "ch-ov-status-board": ("hide", "n/a", "n/a", "n/a"),
    "ch-ov-severity-donut": ("all-panels", "n/a", "n/a", "n/a"),
    "ch-ov-coverage-strips": ("hide", "full", "n/a", "n/a"),
    "ch-ov-last-change": ("hide", "n/a", "n/a", "n/a"),
    "ch-ov-last-frames": ("hide", "n/a", "n/a", "n/a"),
}

_CARD_META: tuple[tuple[str, str, str, str, int], ...] = (
    ("ch-ov-kpi-rings", "overview", "status", "rings", 2),
    ("ch-ov-frames-bars", "overview", "status", "bars-grouped", 1),
    ("ch-ov-status-board", "overview", "status", "board", 3),
    ("ch-ov-severity-donut", "overview", "kpi", "donut", 1),
    ("ch-ov-coverage-strips", "overview", "kpi", "strips", 1),
    ("ch-gr-area-px", "growth", "area-px", "line", 1),
    ("ch-gr-area-cm2", "growth", "area-cm2", "line", 1),
    ("ch-gr-rate-bars", "growth", "rate", "bars-diverging", 1),
    ("ch-gr-daily-bars", "growth", "daily", "bars", 1),
    ("ch-gr-daily-table", "growth", "daily", "table", 1),
    ("ch-ov-last-change", "overview", "status", "line", 2),
    ("ch-ov-last-frames", "overview", "status", "image", 2),
)

_CARD_EN: dict[str, str] = {
    "ch-ov-kpi-rings.title": "Panel health rings",
    "ch-ov-kpi-rings.what": (
        "Four radial gauges per panel: scale coverage, freshness, alert pressure "
        "and shape coverage. Each is a 0–100 % share of the panel's frames."
    ),
    "ch-ov-kpi-rings.how": (
        "Ring fills clockwise from 12 o'clock; the grey track is the full 100 %. "
        "A ring under 50 % is half-empty, not automatically a failure — read the "
        "verdict chip."
    ),
    "ch-ov-kpi-rings.do": (
        "Fix the two lowest rings first: recapture stale panels and re-check the "
        "45 mm scale marker in frames with low coverage."
    ),
    "ch-ov-kpi-rings.now": (
        "Scale coverage {scale_list}; freshness {fresh_list}; shape coverage "
        "{shape_list}."
    ),
    "ch-ov-kpi-rings.conclusion": (
        "{inside} of {panels} panels are within the freshness budget; {worst} is "
        "the binding constraint because {rule} is {rule_value} {unit}."
    ),
    "ch-ov-frames-bars.title": "Frames per UTC day",
    "ch-ov-frames-bars.what": (
        "Grouped bars: one bar per panel per UTC day, counting captured frames."
    ),
    "ch-ov-frames-bars.how": (
        "Compare height inside a panel only; cadence differs between rigs. A "
        "missing day is a gap in the supply, not a zero measurement."
    ),
    "ch-ov-frames-bars.do": (
        "Open Capture › Calendar for hollow days and match every outage to the "
        "capture log before trusting a daily rate."
    ),
    "ch-ov-frames-bars.now": (
        "Frames: {frames_list}; {days} UTC days carry captures in the window "
        "{first} → {last}."
    ),
    "ch-ov-frames-bars.conclusion": (
        "{frames} frames across {panels} panels; the busiest day is {busiest} "
        "with {busiest_count} frames."
    ),
    "ch-ov-status-board.title": "Panel status board",
    "ch-ov-status-board.what": (
        "One row per panel: frames, UTC days, age of the last frame, verdict and "
        "a small area sparkline."
    ),
    "ch-ov-status-board.how": (
        "Read the age and verdict columns first; the sparkline is a shape cue, "
        "not a measurement."
    ),
    "ch-ov-status-board.do": (
        "A stale critical panel is a supply problem: recapture it or archive it "
        "before comparing areas."
    ),
    "ch-ov-status-board.now": (
        "Rows {rows_list}; days {days_list}; age {age_list}; verdict "
        "{verdict_list}."
    ),
    "ch-ov-status-board.conclusion": (
        "{healthy} of {panels} panels are within the freshness budget; {worst} "
        "shows {worst_verdict}."
    ),
    "ch-ov-severity-donut.title": "Findings by severity",
    "ch-ov-severity-donut.what": (
        "Share of deterministic rule findings by severity, with the total in the "
        "centre."
    ),
    "ch-ov-severity-donut.how": (
        "Slices sum to findings, not frames. A big critical slice with a small "
        "centre number means few but severe problems."
    ),
    "ch-ov-severity-donut.do": (
        "Open Alerts › Critical; every critical finding in this build is a "
        "data-supply defect."
    ),
    "ch-ov-severity-donut.now": (
        "{critical} critical, {warn} warning, {ok} ok; {total} findings in total."
    ),
    "ch-ov-severity-donut.conclusion": (
        "{critical} critical and {warn} warning findings; {top_rule} accounts "
        "for {top_count} of them."
    ),
    "ch-ov-coverage-strips.title": "Capture presence strips",
    "ch-ov-coverage-strips.what": (
        "One strip row per panel, one cell per UTC day; filled cells carry frames."
    ),
    "ch-ov-coverage-strips.how": (
        "Read holes before intensity. A hollow day inside a panel's own window "
        "is a rig or queue defect."
    ),
    "ch-ov-coverage-strips.do": (
        "Check the queue for hollow days between a panel's first and last frame."
    ),
    "ch-ov-coverage-strips.now": (
        "{active} of {total} days carry frames; the longest hollow run is "
        "{hollow} days."
    ),
    "ch-ov-coverage-strips.conclusion": (
        "{active} of {total} days in range carry frames; {hollow} days are hollow."
    ),
    "ch-gr-area-px.title": "Projected area (px)",
    "ch-gr-area-px.what": (
        "Silhouette area in pixels per capture on the UTC axis; one path per "
        "continuous capture run."
    ),
    "ch-gr-area-px.how": (
        "Rising means the mask covers more pixels. A break is a capture gap, "
        "never a zero."
    ),
    "ch-gr-area-px.do": (
        "If the last point is below the median and area-drop fires, open the "
        "mask review queue instead of calling it growth."
    ),
    "ch-gr-area-px.now": "{per_panel}",
    "ch-gr-area-px.conclusion": (
        "{panels} panels plotted; the largest swing is {worst} at {delta} %; "
        "breaks are capture gaps, not missing plants."
    ),
    "ch-gr-area-cm2.title": "Projected area (cm²)",
    "ch-gr-area-cm2.what": (
        "Area divided by px_per_mm² and by 100; an × marks every frame where the "
        "45 mm marker was not detected."
    ),
    "ch-gr-area-cm2.how": (
        "The line exists only where a scale was measured. × marks are honest "
        "unknowns; never read a gap as a decrease."
    ),
    "ch-gr-area-cm2.do": (
        "When scale coverage is critical, quote the px trend and chase the "
        "marker in the frames."
    ),
    "ch-gr-area-cm2.now": "{per_panel}",
    "ch-gr-area-cm2.conclusion": (
        "{covered} of {panels} panels have cm² coverage; {worst} covers {pct} % "
        "of its frames."
    ),
    "ch-gr-rate-bars.title": "Day-over-day rate",
    "ch-gr-rate-bars.what": (
        "Change of the daily median area between consecutive UTC days, in "
        "cm²/day (px/day when cm² is unavailable)."
    ),
    "ch-gr-rate-bars.how": (
        "Bars are differences, not levels; zero means no change between two day "
        "medians. Pattern marks the unit fallback."
    ),
    "ch-gr-rate-bars.do": (
        "Compare with growth-stall (|pct| < 2 % over 24 h); one negative bar is "
        "not a stall, three in a row are."
    ),
    "ch-gr-rate-bars.now": "{per_panel}",
    "ch-gr-rate-bars.conclusion": (
        "Direction is up for {up}, down for {down} and flat for {flat} day steps; "
        "the largest step is {value} {unit}/day on {date}."
    ),
    "ch-gr-daily-bars.title": "Daily distribution",
    "ch-gr-daily-bars.what": (
        "Distribution of area_px inside each UTC day: bars are day medians and "
        "the box is min/quartiles/max."
    ),
    "ch-gr-daily-bars.how": (
        "A tall box means the plant or framing moved inside the day; if the box "
        "is taller than the day delta, the delta is noise."
    ),
    "ch-gr-daily-bars.do": (
        "Investigate a day whose box exceeds 25 % of its median before trusting "
        "that day's rate."
    ),
    "ch-gr-daily-bars.now": "{per_panel}",
    "ch-gr-daily-bars.conclusion": (
        "{panel} day medians moved {pct} % across {days} days; the widest "
        "within-day spread is {spread} %."
    ),
    "ch-gr-daily-table.title": "Daily summary table",
    "ch-gr-daily-table.what": (
        "One row per UTC day: frames, median/min/max area and the change against "
        "the previous day."
    ),
    "ch-gr-daily-table.how": (
        "The first day has no delta by definition. A day with no measured rows "
        "shows a dash, never zero."
    ),
    "ch-gr-daily-table.do": (
        "Use the delta column to find the day that broke a trend, then open that "
        "day's distribution card."
    ),
    "ch-gr-daily-table.now": (
        "{days} UTC days; last-day medians {medians_list} px."
    ),
    "ch-gr-daily-table.conclusion": (
        "The table lists {days} days; {measured} of them carry measured areas."
    ),
    "ch-ov-last-change.title": "Change since last frame",
    "ch-ov-last-change.what": (
        "Index of the trailing 24 measured frames per panel, first frame = 100."
    ),
    "ch-ov-last-change.how": (
        "Above 100 means bigger than 24 frames ago; the ±2 % band is the "
        "`growth-stall` threshold."
    ),
    "ch-ov-last-change.now": "{panels_delta}",
    "ch-ov-last-change.do": (
        "If a panel ends outside the ±2 % band, open Growth › area-px for the "
        "same panel."
    ),
    "ch-ov-last-change.conclusion": (
        "{n} of {panels} panels moved outside the ±2 % band over their last 24 "
        "frames; {worst} moved the most."
    ),
    "ch-ov-last-frames.title": "Last frames",
    "ch-ov-last-frames.what": (
        "The last captured frame of each selected panel, with a mask overlay "
        "where a mask exists."
    ),
    "ch-ov-last-frames.how": (
        "Compare framing across panels, not plant size: a shifted frame "
        "invalidates the area step at that timestamp."
    ),
    "ch-ov-last-frames.now": "{frames_state}",
    "ch-ov-last-frames.do": (
        "If framing moved, fix the rig before reading any area delta from the "
        "last day."
    ),
    "ch-ov-last-frames.conclusion": (
        "{frames} last frames embedded from {panels} panels; {missing} panel(s) "
        "have no frame file."
    ),
}

_CARD_RU: dict[str, str] = {
    "ch-ov-kpi-rings.title": "Кольца состояния панелей",
    "ch-ov-kpi-rings.what": (
        "Четыре радиальных индикатора на панель: покрытие масштаба, свежесть, "
        "давление тревог и покрытие формы. Каждый — доля кадров панели от 0 до "
        "100 %."
    ),
    "ch-ov-kpi-rings.how": (
        "Кольцо заполняется по часовой стрелке от 12 часов; серая дорожка — это "
        "все 100 %. Кольцо ниже 50 % означает половину, но не обязательно сбой — "
        "смотрите чип вердикта."
    ),
    "ch-ov-kpi-rings.do": (
        "Сначала исправьте два самых низких кольца: переснимите устаревшие "
        "панели и проверьте маркер масштаба 45 мм на кадрах с низким покрытием."
    ),
    "ch-ov-kpi-rings.now": (
        "Покрытие масштаба {scale_list}; свежесть {fresh_list}; покрытие формы "
        "{shape_list}."
    ),
    "ch-ov-kpi-rings.conclusion": (
        "{inside} из {panels} панелей укладываются в бюджет свежести; «{worst}» — "
        "узкое место, потому что {rule} = {rule_value} {unit}."
    ),
    "ch-ov-frames-bars.title": "Кадры по суткам UTC",
    "ch-ov-frames-bars.what": (
        "Сгруппированные столбцы: по одному на панель за сутки UTC, считая "
        "снятые кадры."
    ),
    "ch-ov-frames-bars.how": (
        "Сравнивайте высоту только внутри панели: частота съёмки у стендов "
        "разная. Пропущенный день — разрыв поставки, а не нулевое измерение."
    ),
    "ch-ov-frames-bars.do": (
        "Откройте «Съёмка › Календарь» для пустых дней и сверьте каждый простой "
        "с журналом съёмки, прежде чем доверять дневному темпу."
    ),
    "ch-ov-frames-bars.now": (
        "Кадры: {frames_list}; съёмка есть за {days} суток UTC в окне {first} → "
        "{last}."
    ),
    "ch-ov-frames-bars.conclusion": (
        "{frames} кадров по {panels} панелям; самый занятый день — {busiest}, "
        "{busiest_count} кадров."
    ),
    "ch-ov-status-board.title": "Сводка по панелям",
    "ch-ov-status-board.what": (
        "По строке на панель: кадры, сутки UTC, возраст последнего кадра, "
        "вердикт и мини-график площади."
    ),
    "ch-ov-status-board.how": (
        "Сначала читайте возраст и вердикт; мини-график показывает форму, а не "
        "измерение."
    ),
    "ch-ov-status-board.do": (
        "Устаревшая критичная панель — проблема поставки: переснимите её или "
        "отправьте в архив, прежде чем сравнивать площади."
    ),
    "ch-ov-status-board.now": (
        "Строки {rows_list}; дни {days_list}; возраст {age_list}; вердикт "
        "{verdict_list}."
    ),
    "ch-ov-status-board.conclusion": (
        "{healthy} из {panels} панелей укладываются в бюджет свежести; «{worst}» — "
        "{worst_verdict}."
    ),
    "ch-ov-severity-donut.title": "Находки по важности",
    "ch-ov-severity-donut.what": (
        "Доля детерминированных находок правил по важности; в центре — общее "
        "число."
    ),
    "ch-ov-severity-donut.how": (
        "Секторы суммируются в находки, а не в кадры. Большой критичный сектор "
        "при малом числе в центре означает мало, но тяжёлых проблем."
    ),
    "ch-ov-severity-donut.do": (
        "Откройте «Тревоги › Критичные»: каждая критичная находка в этой "
        "сборке — дефект поставки данных."
    ),
    "ch-ov-severity-donut.now": (
        "{critical} критичных, {warn} предупреждений, {ok} норм; всего {total} "
        "находок."
    ),
    "ch-ov-severity-donut.conclusion": (
        "{critical} критичных и {warn} предупреждений; {top_rule} даёт "
        "{top_count} из них."
    ),
    "ch-ov-coverage-strips.title": "Полосы присутствия съёмки",
    "ch-ov-coverage-strips.what": (
        "По полосе на панель, по ячейке на сутки UTC; заполненные ячейки "
        "содержат кадры."
    ),
    "ch-ov-coverage-strips.how": (
        "Сначала смотрите на пустоты, потом на интенсивность. Пустой день внутри "
        "окна панели — дефект стенда или очереди."
    ),
    "ch-ov-coverage-strips.do": (
        "Проверьте очередь для пустых дней между первым и последним кадром "
        "панели."
    ),
    "ch-ov-coverage-strips.now": (
        "Кадры есть за {active} из {total} дней; самая длинная пустая серия — "
        "{hollow} дней."
    ),
    "ch-ov-coverage-strips.conclusion": (
        "Кадры есть за {active} из {total} дней диапазона; пустых дней — "
        "{hollow}."
    ),
    "ch-gr-area-px.title": "Проекционная площадь (px)",
    "ch-gr-area-px.what": (
        "Площадь силуэта в пикселях на кадр по оси UTC; один путь на непрерывную "
        "серию съёмки."
    ),
    "ch-gr-area-px.how": (
        "Рост означает, что маска покрывает больше пикселей. Разрыв — это "
        "пропуск съёмки, а не ноль."
    ),
    "ch-gr-area-px.do": (
        "Если последняя точка ниже медианы и сработал area-drop, откройте "
        "очередь проверки масок, а не считайте это ростом."
    ),
    "ch-gr-area-px.now": "{per_panel}",
    "ch-gr-area-px.conclusion": (
        "Построено {panels} панелей; самый большой размах — «{worst}», {delta} %; "
        "разрывы — пропуски съёмки, а не пропавшие растения."
    ),
    "ch-gr-area-cm2.title": "Проекционная площадь (см²)",
    "ch-gr-area-cm2.what": (
        "Площадь, делённая на px_per_mm² и на 100; × отмечает каждый кадр, где "
        "маркер 45 мм не найден."
    ),
    "ch-gr-area-cm2.how": (
        "Линия существует только там, где измерен масштаб. × — честные "
        "неизвестные; не читайте разрыв как уменьшение."
    ),
    "ch-gr-area-cm2.do": (
        "Когда покрытие масштаба критично, цитируйте тренд в px и ищите маркер "
        "на кадрах."
    ),
    "ch-gr-area-cm2.now": "{per_panel}",
    "ch-gr-area-cm2.conclusion": (
        "Покрытие в см² есть у {covered} из {panels} панелей; «{worst}» "
        "покрывает {pct} % кадров."
    ),
    "ch-gr-rate-bars.title": "Темп по дням",
    "ch-gr-rate-bars.what": (
        "Изменение медианной площади между соседними сутками UTC в см²/день "
        "(px/день, когда см² недоступны)."
    ),
    "ch-gr-rate-bars.how": (
        "Столбцы — разности, а не уровни; ноль означает отсутствие изменения "
        "между медианами. Штриховка отмечает запасной вариант единиц."
    ),
    "ch-gr-rate-bars.do": (
        "Сравните с growth-stall (|pct| < 2 % за 24 ч); один отрицательный "
        "столбец — не застой, три подряд — да."
    ),
    "ch-gr-rate-bars.now": "{per_panel}",
    "ch-gr-rate-bars.conclusion": (
        "Направление вверх у {up}, вниз у {down} и ровно у {flat} дневных шагов; "
        "самый большой шаг — {value} {unit}/день, {date}."
    ),
    "ch-gr-daily-bars.title": "Распределение по дням",
    "ch-gr-daily-bars.what": (
        "Распределение area_px внутри каждых суток UTC: столбцы — медианы дней, "
        "ящик — минимум/квартили/максимум."
    ),
    "ch-gr-daily-bars.how": (
        "Высокий ящик означает, что растение или кадрирование сильно сместились "
        "за день; если ящик выше дневной дельты, дельта — шум."
    ),
    "ch-gr-daily-bars.do": (
        "Проверьте день, у которого ящик превышает 25 % медианы, прежде чем "
        "доверять темпу этого дня."
    ),
    "ch-gr-daily-bars.now": "{per_panel}",
    "ch-gr-daily-bars.conclusion": (
        "Медианы «{panel}» сдвинулись на {pct} % за {days} дней; самый широкий "
        "разброс внутри дня — {spread} %."
    ),
    "ch-gr-daily-table.title": "Сводная таблица по дням",
    "ch-gr-daily-table.what": (
        "По строке на сутки UTC: кадры, медиана/минимум/максимум площади и "
        "изменение к предыдущему дню."
    ),
    "ch-gr-daily-table.how": (
        "У первого дня по определению нет дельты. День без измерений показывает "
        "прочерк, а не ноль."
    ),
    "ch-gr-daily-table.do": (
        "По колонке дельты найдите день, сломавший тренд, и откройте карточку "
        "распределения за этот день."
    ),
    "ch-gr-daily-table.now": (
        "{days} суток UTC; медианы последнего дня: {medians_list} px."
    ),
    "ch-gr-daily-table.conclusion": (
        "В таблице {days} дней; у {measured} из них есть измеренные площади."
    ),
    "ch-ov-last-change.title": "Изменение с последнего кадра",
    "ch-ov-last-change.what": (
        "Индекс по последним 24 измеренным кадрам каждой панели, первый кадр = 100."
    ),
    "ch-ov-last-change.how": (
        "Больше 100 — крупнее, чем 24 кадра назад; полоса ±2 % — порог "
        "`growth-stall`."
    ),
    "ch-ov-last-change.now": "{panels_delta}",
    "ch-ov-last-change.do": (
        "Если панель выходит за полосу ±2 %, откройте «Рост › площадь px» для "
        "этой панели."
    ),
    "ch-ov-last-change.conclusion": (
        "За последние 24 кадра {n} из {panels} панелей вышли за полосу ±2 %; "
        "сильнее всех сдвинулась {worst}."
    ),
    "ch-ov-last-frames.title": "Последние кадры",
    "ch-ov-last-frames.what": (
        "Последний снятый кадр каждой выбранной панели с наложением маски, где "
        "маска есть."
    ),
    "ch-ov-last-frames.how": (
        "Сравнивайте кадрирование, а не размер растения: сдвинутый кадр обнуляет "
        "шаг площади на этой метке времени."
    ),
    "ch-ov-last-frames.now": "{frames_state}",
    "ch-ov-last-frames.do": (
        "Если кадрирование сместилось, исправьте установку до чтения любой "
        "дельты площади за последний день."
    ),
    "ch-ov-last-frames.conclusion": (
        "Встроено последних кадров: {frames} для {panels} панелей; у {missing} "
        "панелей нет файла кадра."
    ),
}

TEXTS: dict[str, dict[str, str]] = {
    "en": {**_UI_EN, **_CARD_EN},
    "ru": {**_UI_RU, **_CARD_RU},
}

MISSING_LABELS: dict[str, str] = {
    "measure": "not measured",
    "fact": "not recorded",
    "derived": "not computable",
}

CHIPS: tuple[str, ...] = (
    "critical",
    "warn",
    "ok",
    "not measured",
    "not recorded",
    "not computable",
    "unknown",
)


@dataclass(frozen=True)
class CARD:
    """One registry entry; ``now``/``conclusion`` are computed per payload."""

    id: str
    tab: str
    sub: str
    title: str
    chart: str
    what: str
    how: str
    do: str
    source: str = ""
    span: int = 1


CARDS: tuple[CARD, ...] = tuple(
    CARD(
        id=card_id,
        tab=tab,
        sub=sub,
        title=TEXTS["en"][f"{card_id}.title"],
        chart=chart,
        what=TEXTS["en"][f"{card_id}.what"],
        how=TEXTS["en"][f"{card_id}.how"],
        do=TEXTS["en"][f"{card_id}.do"],
        span=span,
    )
    for card_id, tab, sub, chart, span in _CARD_META
)

ACTIONS: dict[str, str] = {
    "growth-stall": (
        "Compare three consecutive day medians before calling a stall; one flat "
        "day is noise."
    ),
    "area-drop": (
        "Open the mask review queue for the drop window and check framing before "
        "touching thresholds."
    ),
    "solidity-drop": (
        "Inspect the frames for a merged or spilling mask, then re-run "
        "segmentation."
    ),
    "scale-coverage": (
        "Re-check the 45 mm marker in the frames and recalibrate the rig."
    ),
    "capture-gap": (
        "Match the outage to the capture log and restart the queue if no entry "
        "exists."
    ),
    "stale-data": "Recapture the panel or archive it before comparing areas.",
    "quality-flag-rate": (
        "Re-run the series builder with physical quality flags and do not quote "
        "a defect rate until then."
    ),
    "camera-settings-change": (
        "Document the camera-settings change and split the series at that "
        "timestamp."
    ),
    "camera-settings-provenance": (
        "Record exposure, white balance and gain in the sidecar so the pipeline "
        "can separate rig changes."
    ),
}

ACTIONS_RU: dict[str, str] = {
    "growth-stall": (
        "Сравните три подряд дневные медианы, прежде чем называть это застоем; "
        "один ровный день — шум."
    ),
    "area-drop": (
        "Откройте очередь проверки масок за окно падения и проверьте кадрирование, "
        "прежде чем трогать пороги."
    ),
    "solidity-drop": (
        "Проверьте кадры на слившуюся или выходящую за границы маску, затем "
        "перезапустите сегментацию."
    ),
    "scale-coverage": (
        "Перепроверьте маркер 45 мм на кадрах и откалибруйте стенд."
    ),
    "capture-gap": (
        "Сопоставьте простой с журналом съёмки и перезапустите очередь, если "
        "записи о нём нет."
    ),
    "stale-data": (
        "Переснимите панель или отправьте её в архив, прежде чем сравнивать площади."
    ),
    "quality-flag-rate": (
        "Пересоберите серию с физическими флагами качества и не цитируйте долю "
        "дефектов до этого."
    ),
    "camera-settings-change": (
        "Задокументируйте изменение настроек камеры и разделите серию на этой "
        "метке времени."
    ),
    "camera-settings-provenance": (
        "Записывайте выдержку, баланс белого и усиление в sidecar, чтобы конвейер "
        "мог отделять изменения стенда."
    ),
}

# Cards whose charts and copy follow the crop filter; other cards stay
# aggregate by design (their filter scope is ``all-panels``/``hide``).
FRAGMENT_CARDS: frozenset[str] = frozenset(
    {
        "ch-gr-area-px",
        "ch-gr-area-cm2",
        "ch-gr-rate-bars",
        "ch-gr-daily-bars",
        "ch-gr-daily-table",
    }
)

# Conclusions that decompose into one sentence per panel (line/bar cards); the
# daily table keeps its own template with per-panel totals.
PER_PANEL_CONCLUSION: frozenset[str] = frozenset(
    {
        "ch-gr-area-px",
        "ch-gr-area-cm2",
        "ch-gr-rate-bars",
        "ch-gr-daily-bars",
    }
)


def _field(
    name: str, unit: str, kind: str, fmt: str, missing: str
) -> dict[str, str]:
    """One field-dictionary row."""
    return {"name": name, "unit": unit, "type": kind, "fmt": fmt, "missing": missing}


FIELD_DICTIONARY: tuple[dict[str, str], ...] = (
    _field("area_px", "px", "measure", "{:,.0f}", "not measured"),
    _field("area_cm2", "cm²", "derived", "{:,.2f}", "not measured"),
    _field("px_per_mm", "px/mm", "measure", "{:.4f}", "not measured"),
    _field("scale_ok", "bool", "measure", "chip", "not measured"),
    _field("roi_fraction_pct", "%", "measure", "{:.1f} %", "not measured"),
    _field("bbox_w", "px", "measure", "{:.0f}", "not measured"),
    _field("bbox_h", "px", "measure", "{:.0f}", "not measured"),
    _field("width", "px", "fact", "{:.0f}", "never"),
    _field("height", "px", "fact", "{:.0f}", "never"),
    _field("solidity", "ratio", "measure", "{:.3f}", "not measured"),
    _field("extent", "ratio", "measure", "{:.3f}", "not measured"),
    _field("hull_area_px", "px", "measure", "{:,.0f}", "not measured"),
    _field("hull_area_cm2", "cm²", "derived", "{:,.2f}", "not measured"),
    _field("perimeter_px", "px", "measure", "{:,.1f}", "not measured"),
    _field("perimeter_cm", "cm", "derived", "{:,.2f}", "not measured"),
    _field("ellipse_major_px", "px", "measure", "{:,.1f}", "not measured"),
    _field("ellipse_minor_px", "px", "measure", "{:,.1f}", "not measured"),
    _field("n_components", "count", "measure", "{:.0f}", "not measured"),
    _field("captured_at", "UTC", "fact", "%d %b %H:%M", "row excluded"),
    _field("received_at", "UTC", "fact", "%d %b %H:%M", "not recorded"),
    _field("sha256", "—", "fact", "sha16", "never"),
    _field("camera_id", "—", "fact", "verbatim", "unknown"),
    _field("zone_id", "—", "fact", "verbatim", "unknown"),
    _field("experiment_id", "—", "fact", "verbatim", "not recorded"),
    _field("biosource_id", "—", "fact", "verbatim", "not recorded"),
    _field("treatment_id", "—", "fact", "verbatim", "not recorded"),
    _field("light_regime", "—", "fact", "verbatim", "not recorded"),
    _field("exposure_s", "s", "fact", "{:.4f}", "not recorded"),
    _field("white_balance", "—", "fact", "verbatim", "not recorded"),
    _field("gain_db", "dB", "fact", "{:.2f}", "not recorded"),
    _field("settings_source", "—", "fact", "chip", "not recorded"),
    _field("quality_flag", "tokens", "measure", "chips", "not measured"),
    _field("rows", "count", "derived", "{:,}", "0"),
    _field("days", "count", "derived", "{:,}", "—"),
    _field("span_hours", "h", "derived", "{:.1f} h", "not measured"),
    _field("age_days", "d", "derived", "{:.1f} d", "not measured"),
    _field("scale_pct", "%", "derived", "{:.1f} %", "not measured"),
    _field("quality_pct", "%", "derived", "{:.1f} %", "not measured"),
    _field("shape_pct", "%", "derived", "{:.1f} %", "not measured"),
    _field("freshness_pct", "%", "derived", "{:.1f} %", "not measured"),
    _field("area_first", "px", "derived", "{:,.0f}", "not measured"),
    _field("area_last", "px", "derived", "{:,.0f}", "not measured"),
    _field("area_delta_pct", "%", "derived", "{:+.1f} %", "not measured"),
    _field("growth_rate", "unit/d", "derived", "{:+.2f} {unit}", "not computable"),
    _field("index_vs_first", "index", "derived", "{:.1f}", "not measured"),
    _field("day_median", "px", "derived", "{:,}", "not measured"),
    _field("day_min", "px", "derived", "{:,}", "not measured"),
    _field("day_max", "px", "derived", "{:,}", "not measured"),
    _field("gap_hours", "h", "derived", "{:.1f} h", "not measured"),
    _field("verdict", "—", "verdict", "chip", "unknown"),
    _field("severity", "—", "verdict", "chip", "never"),
    _field("rule_id", "—", "verdict", "code", "never"),
    _field("threshold", "rule unit", "verdict", "per rule", "—"),
    _field("value", "rule unit", "verdict", "per rule", "—"),
)

_UNITS: dict[str, dict[str, str]] = {
    "en": {
        "stale-data": "days",
        "scale-coverage": "pt",
        "capture-gap": "h",
        "growth-stall": "%",
        "area-drop": "%",
        "solidity-drop": "pt",
        "quality-flag-rate": "%",
        "camera-settings-change": "combinations",
        "camera-settings-provenance": "%",
    },
    "ru": {
        "stale-data": "дней",
        "scale-coverage": "п.п.",
        "capture-gap": "ч",
        "growth-stall": "%",
        "area-drop": "%",
        "solidity-drop": "п.п.",
        "quality-flag-rate": "%",
        "camera-settings-change": "комбинаций",
        "camera-settings-provenance": "%",
    },
}

_SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2, "unknown": 3}


def _chip(state: str, lang: str) -> str:
    """Localised chip word for a state, falling back to the raw state."""
    key = f"ui.chip.{state}"
    return TEXTS[lang].get(key, state)


def _join(items: Sequence[str], separator: str = " / ") -> str:
    """Join non-empty strings."""
    clean = [item for item in items if item]
    return separator.join(clean)


def _pct(value: float | None, missing: str) -> str:
    """Format a percentage, never a fake zero."""
    return missing if value is None else f"{value:.1f} %"


def _number(value: float | None, decimals: int, unit: str, missing: str) -> str:
    """Format a number with optional unit."""
    if value is None:
        return missing
    suffix = f" {unit}" if unit else ""
    return f"{value:,.{decimals}f}{suffix}"


def _panels(payload: dict[str, object]) -> list[dict[str, object]]:
    """Panel list from a payload."""
    value = payload.get("panels")
    return value if isinstance(value, list) else []


def _findings(payload: dict[str, object]) -> list[dict[str, object]]:
    """Finding list from a payload."""
    value = payload.get("findings")
    return value if isinstance(value, list) else []


def _series(panel: dict[str, object], key: str) -> dict[str, object]:
    """One series block from a panel payload."""
    series = panel.get("series")
    if not isinstance(series, dict):
        return {}
    block = series.get(key)
    return block if isinstance(block, dict) else {}


def _series_stats(panel: dict[str, object], key: str) -> dict[str, float] | None:
    """Statistics dict from one series block."""
    value = _series(panel, key).get("stats")
    return value if isinstance(value, dict) else None


def _binding(panels: Sequence[dict[str, object]]) -> dict[str, object] | None:
    """Panel with the most severe verdict (config order wins ties)."""
    if not panels:
        return None
    return min(panels, key=lambda panel: _SEVERITY_RANK.get(str(panel.get("verdict")), 9))


def _top_rule(findings: Sequence[dict[str, object]]) -> tuple[str, int]:
    """Most frequent rule id with deterministic tie-break."""
    counts: dict[str, int] = {}
    for finding in findings:
        rule = str(finding.get("rule_id", ""))
        counts[rule] = counts.get(rule, 0) + 1
    if not counts:
        return "—", 0
    return min(counts, key=lambda rule: (-counts[rule], rule)), max(counts.values())


def _longest_hollow(cells: Sequence[dict[str, object]]) -> int:
    """Longest consecutive run of zero-frame cells."""
    longest = current = 0
    for cell in cells:
        if int(cell.get("frames", 0)) <= 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _daily_steps(panel: dict[str, object]) -> tuple[list[tuple[float, str, str]], str]:
    """Day-over-day deltas preferring cm² over px."""
    daily = panel.get("daily")
    if not isinstance(daily, list):
        return [], "px"
    cm2 = [
        (str(bucket["date"]), float(bucket["median_area_cm2"]))
        for bucket in daily
        if bucket.get("median_area_cm2") is not None
    ]
    if len(cm2) >= 2:
        series, unit = cm2, "cm²"
    else:
        series = [
            (str(bucket["date"]), float(bucket["median_area_px"]))
            for bucket in daily
            if bucket.get("median_area_px") is not None
        ]
        unit = "px"
    steps = [
        (series[index + 1][1] - series[index][1], unit, series[index + 1][0])
        for index in range(len(series) - 1)
    ]
    return steps, unit


def _values(card_id: str, payload: dict[str, object], lang: str) -> dict[str, str]:
    """Template values for one card in one language."""
    panels = _panels(payload)
    findings = _findings(payload)
    totals = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
    missing = _chip("not-measured", lang)
    dash = "—"
    labels = _join([str(panel.get("label", "")) for panel in panels]) or missing

    if card_id == "ch-ov-kpi-rings":
        scale_list = _join([_pct(panel["kpi"].get("scale_pct"), missing) for panel in panels]) or missing
        fresh_list = _join([_pct(panel["kpi"].get("freshness_pct"), missing) for panel in panels]) or missing
        shape_list = _join([_pct(panel["kpi"].get("shape_pct"), missing) for panel in panels]) or missing
        pressures = []
        for panel in panels:
            alerts = panel.get("alerts") if isinstance(panel.get("alerts"), dict) else {}
            rows = int(panel.get("rows", 0))
            pressure = 100.0 * (1.0 - (3 * int(alerts.get("critical", 0)) + int(alerts.get("warn", 0))) / (3 * max(1, rows)))
            pressures.append(f"{max(0.0, pressure):.1f} %")
        binding = _binding(panels)
        inside = sum(1 for panel in panels if panel.get("verdict") == "ok")
        worst = str(binding.get("label", "")) if binding else dash
        rule = "—"
        rule_value = "0.0"
        unit = ""
        if binding:
            candidates = [item for item in findings if item.get("panel") == binding.get("id")]
            if candidates:
                rule = str(candidates[0].get("rule_id", "—"))
                value = candidates[0].get("value")
                rule_value = f"{float(value):.1f}" if value is not None else dash
                unit = _UNITS[lang].get(rule, "")
        return {
            "scale_list": scale_list,
            "fresh_list": fresh_list,
            "pressure_list": _join(pressures) or missing,
            "shape_list": shape_list,
            "inside": str(inside),
            "panels": str(len(panels)),
            "worst": worst,
            "rule": rule,
            "rule_value": rule_value,
            "unit": unit,
        }

    if card_id == "ch-ov-frames-bars":
        frames_list = _join([str(panel.get("rows", 0)) for panel in panels]) or dash
        calendar = payload.get("calendar") if isinstance(payload.get("calendar"), dict) else {}
        counts: dict[str, int] = {}
        for row in calendar.get("rows", []):
            for cell in row.get("cells", []):
                date = str(cell["date"])
                counts[date] = counts.get(date, 0) + int(cell["frames"])
        busiest = min(counts, key=lambda date: (-counts[date], date)) if counts else dash
        return {
            "frames_list": frames_list,
            "days": str(totals.get("days", 0)),
            "first": str(totals.get("first_at") or "")[:10] or missing,
            "last": str(totals.get("last_at") or "")[:10] or missing,
            "frames": str(totals.get("rows", 0)),
            "panels": str(len(panels)),
            "busiest": busiest,
            "busiest_count": str(counts.get(busiest, 0)),
        }

    if card_id == "ch-ov-status-board":
        binding = _binding(panels)
        return {
            "rows_list": _join([str(panel.get("rows", 0)) for panel in panels]) or dash,
            "days_list": _join([str(panel.get("days", 0)) for panel in panels]) or dash,
            "age_list": _join(
                [_number(panel.get("age_days"), 1, "d", missing) for panel in panels]
            ) or missing,
            "verdict_list": _join(
                [_chip(str(panel.get("verdict", "unknown")), lang) for panel in panels]
            ) or missing,
            "healthy": str(sum(1 for panel in panels if panel.get("verdict") == "ok")),
            "panels": str(len(panels)),
            "worst": str(binding.get("label", "")) if binding else dash,
            "worst_verdict": _chip(str(binding.get("verdict", "unknown")), lang) if binding else missing,
        }

    if card_id == "ch-ov-severity-donut":
        critical = sum(1 for finding in findings if finding.get("severity") == "critical")
        warn = sum(1 for finding in findings if finding.get("severity") == "warn")
        top_rule, top_count = _top_rule(findings)
        return {
            "critical": str(critical),
            "warn": str(warn),
            "ok": str(len(panels) - critical - warn if len(panels) > critical + warn else 0),
            "total": str(len(findings)),
            "top_rule": top_rule,
            "top_count": str(top_count),
        }

    if card_id == "ch-ov-coverage-strips":
        calendar = payload.get("calendar") if isinstance(payload.get("calendar"), dict) else {}
        rows = calendar.get("rows", [])
        total = len(rows[0].get("cells", [])) if rows else 0
        hollow = max((_longest_hollow(row.get("cells", [])) for row in rows), default=0)
        return {
            "active": str(calendar.get("days", 0)),
            "total": str(total),
            "hollow": str(hollow),
        }

    if card_id == "ch-gr-area-px":
        lines: list[str] = []
        swings: list[tuple[float, str, float]] = []
        for panel in panels:
            stats = _series_stats(panel, "area_px")
            label = str(panel.get("label", ""))
            if not stats:
                lines.append(f"{label}: {missing}")
                continue
            first, last = stats["first"], stats["last"]
            delta = (last - first) / first * 100.0 if first > 0 else None
            lines.append(
                f"{label}: {first:,.0f} → {last:,.0f} px "
                f"({delta:+.1f} %)" if delta is not None else f"{label}: {first:,.0f} → {last:,.0f} px"
            )
            if delta is not None:
                swings.append((abs(delta), label, delta))
        worst = max(swings, key=lambda item: item[0]) if swings else None
        return {
            "per_panel": _join(lines, "; ") or missing,
            "panels": str(len(panels)),
            "worst": worst[1] if worst else dash,
            "delta": f"{worst[2]:+.1f}" if worst else dash,
        }

    if card_id == "ch-gr-area-cm2":
        lines: list[str] = []
        coverages: list[tuple[float, str]] = []
        covered = 0
        for panel in panels:
            block = _series(panel, "area_cm2")
            measured = int(block.get("measured", 0))
            source = int(block.get("source_points", 0)) or measured
            stats = block.get("stats")
            label = str(panel.get("label", ""))
            if measured <= 0 or not stats:
                lines.append(f"{label}: {missing}")
                coverages.append((0.0, label))
                continue
            covered += 1
            coverage = 100.0 * measured / source if source else 0.0
            coverages.append((coverage, label))
            lines.append(
                f"{label}: {measured}/{source} ({coverage:.1f} %), "
                f"{stats['first']:,.2f} → {stats['last']:,.2f} cm²"
            )
        worst = min(coverages, key=lambda item: item[0]) if coverages else None
        return {
            "per_panel": _join(lines, "; ") or missing,
            "covered": str(covered),
            "panels": str(len(panels)),
            "worst": worst[1] if worst else dash,
            "pct": f"{worst[0]:.1f}" if worst else dash,
        }

    if card_id == "ch-gr-rate-bars":
        lines: list[str] = []
        all_steps: list[tuple[float, str, str]] = []
        for panel in panels:
            steps, unit = _daily_steps(panel)
            label = str(panel.get("label", ""))
            all_steps.extend(steps)
            if not steps:
                lines.append(f"{label}: {_chip('not-computable', lang)}")
                continue
            lines.append(
                f"{label}: {steps[0][0]:+.2f} → {steps[-1][0]:+.2f} {unit}/day"
            )
        up = sum(1 for value, _unit, _date in all_steps if value > 0.05)
        down = sum(1 for value, _unit, _date in all_steps if value < -0.05)
        flat = len(all_steps) - up - down
        largest = max(all_steps, key=lambda item: abs(item[0])) if all_steps else None
        return {
            "per_panel": _join(lines, "; ") or missing,
            "up": str(up),
            "down": str(down),
            "flat": str(flat),
            "value": f"{largest[0]:+.2f}" if largest else dash,
            "unit": largest[1] if largest else "",
            "date": largest[2] if largest else dash,
        }

    if card_id == "ch-gr-daily-bars":
        lines: list[str] = []
        spreads: list[tuple[float, str]] = []
        for panel in panels:
            daily = panel.get("daily") if isinstance(panel.get("daily"), list) else []
            medians = [
                (str(bucket["date"]), float(bucket["median_area_px"]))
                for bucket in daily
                if bucket.get("median_area_px") is not None
            ]
            label = str(panel.get("label", ""))
            if not medians:
                lines.append(f"{label}: {missing}")
                continue
            values = [value for _date, value in medians]
            median = values[len(values) // 2]
            spread = (max(values) - min(values)) / median * 100.0 if median > 0 else None
            lines.append(
                f"{label}: {len(values)} days, {min(values):,.0f}–{max(values):,.0f} px, "
                f"median {median:,.0f}"
            )
            if spread is not None:
                spreads.append((spread, label))
        first_panel = panels[0] if panels else {}
        daily = first_panel.get("daily") if isinstance(first_panel.get("daily"), list) else []
        medians = [
            float(bucket["median_area_px"])
            for bucket in daily
            if bucket.get("median_area_px") is not None
        ]
        movement = (
            (medians[-1] - medians[0]) / medians[0] * 100.0
            if len(medians) >= 2 and medians[0] > 0
            else None
        )
        widest = max(spreads, key=lambda item: item[0]) if spreads else None
        return {
            "per_panel": _join(lines, "; ") or missing,
            "panel": str(first_panel.get("label", "")) or dash,
            "pct": f"{movement:+.1f}" if movement is not None else dash,
            "days": str(len(medians)),
            "spread": f"{widest[0]:.1f}" if widest else dash,
        }

    if card_id == "ch-gr-daily-table":
        medians: list[str] = []
        measured_days: set[str] = set()
        for panel in panels:
            daily = panel.get("daily") if isinstance(panel.get("daily"), list) else []
            for bucket in daily:
                if bucket.get("median_area_px") is not None:
                    measured_days.add(str(bucket.get("date", "")))
            last = next(
                (
                    bucket
                    for bucket in reversed(daily)
                    if bucket.get("median_area_px") is not None
                ),
                None,
            )
            if last is None:
                continue
            label = str(panel.get("label", "")).split(" · ")[0]
            medians.append(f"{label} {float(last['median_area_px']):,.0f}")
        return {
            "days": str(totals.get("days", 0)),
            "medians_list": _join(medians, "; ") or missing,
            "measured": str(len(measured_days)),
        }

    if card_id == "ch-ov-last-change":
        lines: list[str] = []
        moves: list[tuple[float, str]] = []
        outside = 0
        for panel in panels:
            series = (
                panel.get("last_change")
                if isinstance(panel.get("last_change"), list)
                else []
            )
            label = str(panel.get("label", ""))
            if not series:
                lines.append(f"{label}: {missing}")
                continue
            last = float(series[-1][1])
            delta = last - 100.0
            lines.append(f"{label}: {last:.1f} ({delta:+.1f} %)")
            moves.append((abs(delta), label))
            if abs(delta) > 2.0:
                outside += 1
        worst = max(moves, key=lambda item: item[0])[1] if moves else dash
        return {
            "panels_delta": _join(lines, "; ") or missing,
            "n": str(outside),
            "panels": str(len(panels)),
            "worst": worst,
        }

    if card_id == "ch-ov-last-frames":
        records = (
            payload.get("frames") if isinstance(payload.get("frames"), list) else []
        )
        last_records = [
            record
            for record in records
            if isinstance(record, dict)
            and int(record.get("total", 0) or 0) > 0
            and int(record.get("index", -1) or -1)
            == int(record.get("total", 0) or 0) - 1
        ]
        present = {str(record.get("panel", "")) for record in last_records}
        frames = len(last_records)
        absent = sum(1 for panel in panels if str(panel.get("id", "")) not in present)
        frames_state = (
            f"{frames} of {len(panels)} panels have a last frame"
            if frames
            else _chip("not-recorded", lang)
        )
        return {
            "frames_state": frames_state,
            "frames": str(frames),
            "panels": str(len(panels)),
            "missing": str(absent),
        }

    raise ValueError(f"no values for {card_id}")


def _fill(template: str, values: dict[str, str]) -> str:
    """Fill a template and normalise whitespace."""
    return " ".join(template.format(**values).split())


def _now_text(card_id: str, payload: dict[str, object], lang: str) -> str:
    """Compute the localised ``now`` sentence for a card."""
    return _fill(TEXTS[lang][f"{card_id}.now"], _values(card_id, payload, lang))


def conclusion(card_id: str, payload: dict[str, object], lang: str = "en") -> str:
    """Compute the localised conclusion sentence for a card.

    Args:
        card_id: Registry id.
        payload: Page payload.
        lang: ``en`` or ``ru``.

    Returns:
        The filled sentence.

    Raises:
        ValueError: For an unknown card id or language.
    """
    key = f"{card_id}.conclusion"
    if key not in TEXTS.get(lang, {}):
        raise ValueError(f"no conclusion for {card_id}")
    return _fill(TEXTS[lang][key], _values(card_id, payload, lang))


def _state(card_id: str, payload: dict[str, object]) -> str:
    """Card data state used by the chip."""
    panels = _panels(payload)
    if not panels:
        return "not-measured"
    if card_id == "ch-gr-area-cm2":
        if all(int(_series(panel, "area_cm2").get("measured", 0)) == 0 for panel in panels):
            return "not-measured"
    if card_id == "ch-gr-rate-bars":
        if all(
            sum(
                1
                for bucket in panel.get("daily", [])
                if bucket.get("median_area_px") is not None
            )
            < 2
            for panel in panels
        ):
            return "not-computable"
    if card_id == "ch-ov-last-change":
        if all(not panel.get("last_change") for panel in panels):
            return "not-measured"
    if card_id == "ch-ov-last-frames":
        records = (
            payload.get("frames") if isinstance(payload.get("frames"), list) else []
        )
        if not records:
            return "not-measured"
    return "ok"


def _card_stats(card_id: str, payload: dict[str, object]) -> list[dict[str, str]]:
    """Drawer stats: same payload fields as the card (D19)."""
    panels = _panels(payload)
    key = "area_cm2" if card_id == "ch-gr-area-cm2" else "area_px"
    if card_id.startswith("ch-gr-") and card_id != "ch-gr-daily-table":
        items: list[dict[str, str]] = []
        for panel in panels:
            block = _series(panel, key)
            stats = block.get("stats") or {}
            count = f"{float(stats.get('n', 0)):g}"
            items.append(
                {
                    "label_en": str(panel.get("label", "")),
                    "label_ru": str(panel.get("label", "")),
                    "value_en": (
                        f"n {count} · {TEXTS['en']['ui.stats.measured']} "
                        f"{block.get('measured', 0)} · "
                        f"{TEXTS['en']['ui.stats.missing']} {block.get('missing', 0)}"
                    ),
                    "value_ru": (
                        f"n {count} · {TEXTS['ru']['ui.stats.measured']} "
                        f"{block.get('measured', 0)} · "
                        f"{TEXTS['ru']['ui.stats.missing']} {block.get('missing', 0)}"
                    ),
                }
            )
        return items
    return [
        {
            "label_en": TEXTS["en"]["ui.stats.panels"],
            "label_ru": TEXTS["ru"]["ui.stats.panels"],
            "value_en": str(len(panels)),
            "value_ru": str(len(panels)),
        },
        {
            "label_en": TEXTS["en"]["ui.stats.frames"],
            "label_ru": TEXTS["ru"]["ui.stats.frames"],
            "value_en": str(
                (payload.get("totals") or {}).get("rows", 0)
                if isinstance(payload.get("totals"), dict)
                else 0
            ),
            "value_ru": str(
                (payload.get("totals") or {}).get("rows", 0)
                if isinstance(payload.get("totals"), dict)
                else 0
            ),
        },
    ]


_CARD_AXIS_UNIT: dict[str, str] = {
    "ch-ov-frames-bars": "count",
    "ch-gr-area-px": "px",
    "ch-gr-area-cm2": "cm²",
    "ch-gr-rate-bars": "%",
    "ch-gr-daily-bars": "px",
}

_CHART_AXIS_UNIT: dict[str, str] = {
    "line": "px",
    "area": "px",
    "bars": "px",
    "bars-grouped": "count",
    "bars-diverging": "%",
}


def _card_axes(card_id: str) -> dict[str, str]:
    """Drawer axis block with the unit the card actually plots."""
    card = next((item for item in CARDS if item.id == card_id), None)
    if card is None or card.chart not in _CHART_AXIS_UNIT:
        return {}
    unit = _CARD_AXIS_UNIT.get(card_id, _CHART_AXIS_UNIT[card.chart])
    return {
        "x_en": "captured_at (UTC)",
        "x_ru": "captured_at (UTC)",
        "y_en": unit,
        "y_ru": unit,
        "step_en": "automatic",
        "step_ru": "автоматически",
    }


def _card_thresholds(card_id: str) -> list[dict[str, str]]:
    """Drawer threshold block read from :class:`RuleConfig` (no literals)."""
    config = RuleConfig()
    if card_id == "ch-ov-kpi-rings":
        return [
            {
                "label_en": f"warn age {config.stale_warn_days:g} d",
                "label_ru": f"предупреждение {config.stale_warn_days:g} д",
                "value": f"{config.stale_warn_days:g} d",
                "at": config.stale_warn_days,
                "unit": "d",
                "kind": "warn",
            },
            {
                "label_en": f"critical age {config.stale_critical_days:g} d",
                "label_ru": f"критично {config.stale_critical_days:g} д",
                "value": f"{config.stale_critical_days:g} d",
                "at": config.stale_critical_days,
                "unit": "d",
                "kind": "critical",
            },
        ]
    if card_id == "ch-gr-area-px":
        return [
            {
                "label_en": f"area-drop warn {config.area_drop_warn_pct:g} %",
                "label_ru": f"area-drop предупреждение {config.area_drop_warn_pct:g} %",
                "value": f"{config.area_drop_warn_pct:g} %",
                "at": config.area_drop_warn_pct,
                "unit": "%",
                "kind": "warn",
            },
            {
                "label_en": f"area-drop critical {config.area_drop_critical_pct:g} %",
                "label_ru": f"area-drop критично {config.area_drop_critical_pct:g} %",
                "value": f"{config.area_drop_critical_pct:g} %",
                "at": config.area_drop_critical_pct,
                "unit": "%",
                "kind": "critical",
            },
        ]
    if card_id == "ch-gr-rate-bars":
        return [
            {
                "label_en": f"growth-stall {config.growth_stall_min_pct:g} %",
                "label_ru": f"growth-stall {config.growth_stall_min_pct:g} %",
                "value": f"{config.growth_stall_min_pct:g} %",
                "at": config.growth_stall_min_pct,
                "unit": "%",
                "kind": "warn",
            }
        ]
    return []


def _sub_payload(
    payload: dict[str, object], panel: dict[str, object]
) -> dict[str, object]:
    """Project a payload onto one panel for per-panel fragment formatting."""
    out = dict(payload)
    out["panels"] = [panel]
    out["findings"] = [
        finding
        for finding in _findings(payload)
        if finding.get("panel") == panel.get("id")
    ]
    totals = dict(payload.get("totals") or {})
    totals["days"] = int(panel.get("days", totals.get("days", 0)) or 0)
    out["totals"] = totals
    return out


def _span_text(hours: object, lang: str) -> str | None:
    """Human capture span, in days once it passes two full days."""
    if hours is None:
        return None
    try:
        value = float(hours)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    if value >= 48.0:
        unit = "days" if lang == "en" else "дн."
        return f"{value / 24.0:.1f} {unit}"
    unit = "h" if lang == "en" else "ч"
    return f"{value:.1f} {unit}"


def _single_record(
    card_id: str, payload: dict[str, object]
) -> dict[str, object] | None:
    """Compact one-panel summary values, or ``None`` when unavailable."""
    panels = _panels(payload)
    if len(panels) != 1:
        return None
    panel = panels[0]
    span_hours = panel.get("span_hours")
    if span_hours is None:
        return None
    try:
        span_value = float(span_hours)
    except (TypeError, ValueError):
        return None
    if span_value < 0:
        return None
    unit = ""
    first_text = last_text = ""
    delta: str | None = None
    if card_id == "ch-gr-area-px":
        stats = _series_stats(panel, "area_px")
        if not stats:
            return None
        first, last = stats["first"], stats["last"]
        unit = "px"
        delta = f"{(last - first) / first * 100.0:+.1f} %" if first > 0 else None
        first_text, last_text = f"{first:,.0f}", f"{last:,.0f}"
    elif card_id == "ch-gr-area-cm2":
        block = _series(panel, "area_cm2")
        stats = block.get("stats")
        if int(block.get("measured", 0) or 0) <= 0 or not isinstance(stats, dict):
            return None
        first, last = float(stats["first"]), float(stats["last"])
        unit = "cm²"
        delta = f"{(last - first) / first * 100.0:+.1f} %" if first > 0 else None
        first_text, last_text = f"{first:,.2f}", f"{last:,.2f}"
    elif card_id == "ch-gr-rate-bars":
        steps, base_unit = _daily_steps(panel)
        if not steps:
            return None
        first, last = steps[0][0], steps[-1][0]
        unit = f"{base_unit}/day"
        delta = f"{last - first:+.2f} {unit}"
        first_text, last_text = f"{first:+.2f}", f"{last:+.2f}"
    elif card_id == "ch-gr-daily-bars":
        daily = panel.get("daily") if isinstance(panel.get("daily"), list) else []
        medians = [
            float(bucket["median_area_px"])
            for bucket in daily
            if bucket.get("median_area_px") is not None
        ]
        if not medians:
            return None
        first, last = medians[0], medians[-1]
        unit = "px"
        delta = f"{(last - first) / first * 100.0:+.1f} %" if first > 0 else None
        first_text, last_text = f"{first:,.0f}", f"{last:,.0f}"
    else:
        return None
    if delta is None:
        return None
    return {
        "first": first_text,
        "last": last_text,
        "delta": delta,
        "span_hours": span_value,
        "unit": unit,
    }


def _single_conclusion(
    card_id: str, payload: dict[str, object], lang: str
) -> str | None:
    """Distinct one-panel conclusion for a single-crop selection."""
    panels = _panels(payload)
    if len(panels) != 1:
        return None
    label = str(panels[0].get("label", ""))
    record = _single_record(card_id, payload)
    if not label or record is None:
        return None
    span = _span_text(record["span_hours"], lang)
    if span is None:
        return None
    return _fill(
        TEXTS[lang]["ui.conclusion.single"],
        {
            "panel": label,
            "delta": str(record["delta"]),
            "span": span,
            "first": str(record["first"]),
            "last": str(record["last"]),
            "unit": str(record["unit"]),
        },
    )


def _single_fragments(
    card_id: str, payload: dict[str, object]
) -> dict[str, dict[str, str]]:
    """One-panel conclusion summaries keyed by panel id, per language."""
    out: dict[str, dict[str, str]] = {}
    for panel in _panels(payload):
        panel_id = str(panel.get("id", ""))
        if not panel_id:
            continue
        out[panel_id] = {}
        for lang in ("en", "ru"):
            text = _single_conclusion(card_id, _sub_payload(payload, panel), lang)
            out[panel_id][lang] = text if text is not None else _chip(
                "not-computable", lang
            )
    return out


def _single_values(card_id: str, payload: dict[str, object]) -> dict[str, object]:
    """Compact per-panel summary values for the client renderer."""
    out: dict[str, object] = {}
    for panel in _panels(payload):
        panel_id = str(panel.get("id", ""))
        if panel_id:
            out[panel_id] = _single_record(
                card_id, _sub_payload(payload, panel)
            )
    return out


def _fragment(
    card_id: str,
    payload: dict[str, object],
    panel: dict[str, object],
    field: str,
    lang: str,
) -> str:
    """Formatted per-panel ``now``/``conclusion`` fragment for one card."""
    sub = _sub_payload(payload, panel)
    if field == "conclusion" and card_id in PER_PANEL_CONCLUSION:
        return str(_values(card_id, sub, lang).get("per_panel") or "")
    if field == "conclusion":
        return conclusion(card_id, sub, lang)
    return _now_text(card_id, sub, lang)


def _panel_fragments(
    card_id: str, payload: dict[str, object], field: str
) -> dict[str, dict[str, str]]:
    """Per-panel fragments keyed by panel id, already formatted per language."""
    parts: dict[str, dict[str, str]] = {}
    for panel in _panels(payload):
        panel_id = str(panel.get("id", ""))
        if not panel_id:
            continue
        parts[panel_id] = {
            lang: _fragment(card_id, payload, panel, field, lang)
            for lang in ("en", "ru")
        }
    return parts


def _do_actions(payload: dict[str, object]) -> dict[str, dict[str, str]]:
    """Critical action per panel, keyed by panel id (first critical rule wins)."""
    actions: dict[str, dict[str, str]] = {}
    for finding in _findings(payload):
        if finding.get("severity") != "critical":
            continue
        panel_id = str(finding.get("panel", ""))
        if not panel_id or panel_id in actions:
            continue
        rule = str(finding.get("rule_id", ""))
        actions[panel_id] = {
            "en": ACTIONS.get(rule, ""),
            "ru": ACTIONS_RU.get(rule, ""),
        }
    return actions


def join_fragments(
    card: dict[str, object],
    field: str,
    selected: Sequence[str],
    lang: str = "en",
) -> str:
    """Join selected panel fragments with ``; `` using the card join template.

    Args:
        card: One payload card record.
        field: ``now`` or ``conclusion``.
        selected: Panel ids in config order.
        lang: ``en`` or ``ru``.

    Returns:
        The rendered sentence. A single selected panel gets the compact
        one-panel summary; two or more panels use the precomputed aggregate
        sentence. The ``now`` field keeps its per-panel value lines.
    """
    parts_map = card.get(f"{field}_parts")
    if field == "conclusion" and len(selected) >= 2:
        return str(card.get(f"{field}_{lang}", ""))
    if not isinstance(parts_map, dict):
        return str(card.get(f"{field}_{lang}", ""))
    if len(selected) == len(parts_map):
        return str(card.get(f"{field}_{lang}", ""))
    parts = [
        str((parts_map.get(panel_id) or {}).get(lang, ""))
        for panel_id in selected
        if isinstance(parts_map.get(panel_id), dict)
    ]
    parts = [part for part in parts if part]
    template_map = card.get(f"{field}_join")
    template = (
        str(template_map.get(lang, "{parts}"))
        if isinstance(template_map, dict)
        else "{parts}"
    )
    return template.replace("{parts}", "; ".join(parts))


def cards_for_payload(payload: dict[str, object]) -> list[dict[str, object]]:
    """Build the card/drawer records shared by the grid and the drawer.

    Args:
        payload: Page payload.

    Returns:
        One dict per registry card, in registry order.
    """
    records: list[dict[str, object]] = []
    do_actions = _do_actions(payload)
    for card in CARDS:
        values_en = _values(card.id, payload, "en")
        values_ru = _values(card.id, payload, "ru")
        scope = FILTER_SCOPE[card.id]
        records.append(
            {
                "id": card.id,
                "tab": card.tab,
                "sub": card.sub,
                "chart": card.chart,
                "source": card.source,
                "state": _state(card.id, payload),
                "span": card.span,
                "filter": {
                    "crop": scope[0],
                    "window": scope[1],
                    "agg": scope[2],
                    "mode": scope[3],
                },
                "filter_scope": (
                    scope[0]
                    if scope[1] == scope[2] == scope[3] == "hide"
                    else "mixed"
                ),
                "render": (
                    "client"
                    if card.id
                    in {
                        "ch-gr-area-px",
                        "ch-gr-area-cm2",
                        "ch-gr-rate-bars",
                        "ch-gr-daily-bars",
                        "ch-gr-daily-table",
                    }
                    else "static"
                ),
                "key": (
                    "area_cm2"
                    if card.id == "ch-gr-area-cm2"
                    else "area_px"
                    if card.id
                    in {
                        "ch-gr-area-px",
                        "ch-gr-rate-bars",
                        "ch-gr-daily-bars",
                    }
                    else ""
                ),
                "title_en": TEXTS["en"][f"{card.id}.title"],
                "title_ru": TEXTS["ru"][f"{card.id}.title"],
                "what_en": TEXTS["en"][f"{card.id}.what"],
                "what_ru": TEXTS["ru"][f"{card.id}.what"],
                "how_en": TEXTS["en"][f"{card.id}.how"],
                "how_ru": TEXTS["ru"][f"{card.id}.how"],
                "now_en": _fill(TEXTS["en"][f"{card.id}.now"], values_en),
                "now_ru": _fill(TEXTS["ru"][f"{card.id}.now"], values_ru),
                "now_parts": (
                    _panel_fragments(card.id, payload, "now")
                    if card.id in FRAGMENT_CARDS
                    else {}
                ),
                "now_join": {"en": "{parts}", "ru": "{parts}"},
                "do_en": TEXTS["en"][f"{card.id}.do"],
                "do_ru": TEXTS["ru"][f"{card.id}.do"],
                "do_ok": (
                    {
                        "en": TEXTS["en"]["ui.do.ok"],
                        "ru": TEXTS["ru"]["ui.do.ok"],
                    }
                    if card.id in FRAGMENT_CARDS
                    else {}
                ),
                "do_actions": do_actions if card.id in FRAGMENT_CARDS else {},
                "conclusion_en": _fill(
                    TEXTS["en"][f"{card.id}.conclusion"], values_en
                ),
                "conclusion_ru": _fill(
                    TEXTS["ru"][f"{card.id}.conclusion"], values_ru
                ),
                "conclusion_parts": (
                    _single_fragments(card.id, payload)
                    if card.id in PER_PANEL_CONCLUSION
                    else _panel_fragments(card.id, payload, "conclusion")
                    if card.id in FRAGMENT_CARDS
                    else {}
                ),
                "single_values": (
                    _single_values(card.id, payload)
                    if card.id in PER_PANEL_CONCLUSION
                    else {}
                ),
                "conclusion_join": {"en": "{parts}", "ru": "{parts}"},
                "stats": _card_stats(card.id, payload),
                "axes": _card_axes(card.id),
                "thresholds": _card_thresholds(card.id),
            }
        )
    return records


