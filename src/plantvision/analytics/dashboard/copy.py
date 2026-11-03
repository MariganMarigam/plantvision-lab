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
}

_CARD_META: tuple[tuple[str, str, str, str], ...] = (
    ("ch-ov-kpi-rings", "overview", "status", "rings"),
    ("ch-ov-frames-bars", "overview", "status", "bars-grouped"),
    ("ch-ov-status-board", "overview", "status", "board"),
    ("ch-ov-severity-donut", "overview", "kpi", "donut"),
    ("ch-ov-coverage-strips", "overview", "kpi", "strips"),
    ("ch-gr-area-px", "growth", "area-px", "line"),
    ("ch-gr-area-cm2", "growth", "area-cm2", "line"),
    ("ch-gr-rate-bars", "growth", "rate", "bars-diverging"),
    ("ch-gr-daily-bars", "growth", "daily", "bars"),
    ("ch-gr-daily-table", "growth", "daily", "table"),
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
        "{inside} of {panels} panels are inside budget; {worst} is the binding "
        "constraint because {rule} is {rule_value} {unit}."
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
        "{healthy} of {panels} panels are inside budget; {worst} shows "
        "{worst_verdict}."
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
        "{inside} из {panels} панелей в пределах бюджета; «{worst}» — узкое "
        "место, потому что {rule} = {rule_value} {unit}."
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
        "{healthy} из {panels} панелей в пределах бюджета; «{worst}» — "
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
    )
    for card_id, tab, sub, chart in _CARD_META
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


def _card_axes(card_id: str) -> dict[str, str]:
    """Drawer axis block (empty for non-cartesian cards)."""
    card = next((item for item in CARDS if item.id == card_id), None)
    if card is None or card.chart not in {"line", "area", "bars", "bars-grouped", "bars-diverging"}:
        return {}
    return {
        "x_en": "captured_at (UTC)",
        "x_ru": "captured_at (UTC)",
        "y_en": "value",
        "y_ru": "значение",
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
                "kind": "warn",
            },
            {
                "label_en": f"critical age {config.stale_critical_days:g} d",
                "label_ru": f"критично {config.stale_critical_days:g} д",
                "value": f"{config.stale_critical_days:g} d",
                "kind": "critical",
            },
        ]
    if card_id == "ch-gr-area-px":
        return [
            {
                "label_en": f"area-drop warn {config.area_drop_warn_pct:g} %",
                "label_ru": f"area-drop предупреждение {config.area_drop_warn_pct:g} %",
                "value": f"{config.area_drop_warn_pct:g} %",
                "kind": "warn",
            },
            {
                "label_en": f"area-drop critical {config.area_drop_critical_pct:g} %",
                "label_ru": f"area-drop критично {config.area_drop_critical_pct:g} %",
                "value": f"{config.area_drop_critical_pct:g} %",
                "kind": "critical",
            },
        ]
    if card_id == "ch-gr-rate-bars":
        return [
            {
                "label_en": f"growth-stall {config.growth_stall_min_pct:g} %",
                "label_ru": f"growth-stall {config.growth_stall_min_pct:g} %",
                "value": f"{config.growth_stall_min_pct:g} %",
                "kind": "warn",
            }
        ]
    return []


def cards_for_payload(payload: dict[str, object]) -> list[dict[str, object]]:
    """Build the card/drawer records shared by the grid and the drawer.

    Args:
        payload: Page payload.

    Returns:
        One dict per registry card, in registry order.
    """
    records: list[dict[str, object]] = []
    for card in CARDS:
        values_en = _values(card.id, payload, "en")
        values_ru = _values(card.id, payload, "ru")
        records.append(
            {
                "id": card.id,
                "tab": card.tab,
                "sub": card.sub,
                "chart": card.chart,
                "source": card.source,
                "state": _state(card.id, payload),
                "title_en": TEXTS["en"][f"{card.id}.title"],
                "title_ru": TEXTS["ru"][f"{card.id}.title"],
                "what_en": TEXTS["en"][f"{card.id}.what"],
                "what_ru": TEXTS["ru"][f"{card.id}.what"],
                "how_en": TEXTS["en"][f"{card.id}.how"],
                "how_ru": TEXTS["ru"][f"{card.id}.how"],
                "now_en": _fill(TEXTS["en"][f"{card.id}.now"], values_en),
                "now_ru": _fill(TEXTS["ru"][f"{card.id}.now"], values_ru),
                "do_en": TEXTS["en"][f"{card.id}.do"],
                "do_ru": TEXTS["ru"][f"{card.id}.do"],
                "conclusion_en": _fill(
                    TEXTS["en"][f"{card.id}.conclusion"], values_en
                ),
                "conclusion_ru": _fill(
                    TEXTS["ru"][f"{card.id}.conclusion"], values_ru
                ),
                "stats": _card_stats(card.id, payload),
                "axes": _card_axes(card.id),
                "thresholds": _card_thresholds(card.id),
            }
        )
    return records


