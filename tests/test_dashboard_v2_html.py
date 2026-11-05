"""Document-level contract tests for the v2 shell (Gate 1)."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from plantvision.analytics.dashboard.build import Panel, build_report, load_panels
from plantvision.analytics.dashboard.copy import TEXTS
from plantvision.analytics.dashboard.layout import CSS
from plantvision.analytics.timeseries import TIMESERIES_COLUMNS

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def _write_csv(path: Path, *, offset: int, rows: int = 8) -> None:
    """Write one small valid store."""
    start = datetime(2026, 10, 20 + offset, 6, 0, tzinfo=timezone.utc)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TIMESERIES_COLUMNS)
        writer.writeheader()
        for index in range(rows):
            row = {column: "" for column in TIMESERIES_COLUMNS}
            row.update(
                {
                    "sha256": f"{offset:02d}{index:06d}" + "0" * 56,
                    "captured_at": (start + timedelta(minutes=5 * index))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "camera_id": f"cam-{offset}",
                    "zone_id": f"zone-{offset}",
                    "width": "1280",
                    "height": "720",
                    "px_per_mm": "4.0",
                    "area_px": "" if offset == 2 else str(1000 + offset * 100 + index * 10),
                    "area_cm2": f"{12.0 + index:.3f}",
                    "roi_fraction_pct": "20.0",
                    "solidity": "0.6",
                    "extent": "0.5",
                    "bbox_w": "40",
                    "bbox_h": "30",
                    "perimeter_px": "140",
                    "ellipse_major_px": "50",
                    "ellipse_minor_px": "30",
                    "scale_ok": "true",
                    "quality_flag": "ok" if offset != 1 else "",
                    "settings_source": "exif",
                }
            )
            writer.writerow(row)


def _panels(root: Path) -> list[Panel]:
    """Three synthetic panels in a temp directory."""
    panels = []
    for offset in range(3):
        path = root / f"store-{offset}.csv"
        _write_csv(path, offset=offset)
        panels.append(
            Panel(
                id=f"panel-{offset}",
                label=f"Panel {offset}",
                crop="crop",
                method="sam2" if offset == 0 else "exg",
                method_label="method",
                csv_path=path,
                pipeline_version=f"p{offset}",
                note="note",
            )
        )
    return panels


@pytest.fixture(scope="module")
def page(tmp_path_factory: pytest.TempPathFactory):
    """Build one page from synthetic stores and return (html, result, panels)."""
    root = tmp_path_factory.mktemp("dashboard-html")
    panels = _panels(root)
    out = root / "index.html"
    result = build_report(
        panels, out, now=NOW, title="Test dashboard", include_frames=False
    )
    return out.read_text(encoding="utf-8"), result, panels


def _card_markup(html: str, card_id: str) -> str:
    """Extract one card article from the document."""
    match = re.search(
        rf'<article class="pv-card" id="pv-card-{re.escape(card_id)}".*?</article>',
        html,
        re.S,
    )
    assert match is not None, card_id
    return match.group(0)


def test_every_tab_and_subtab_id_unique(page) -> None:
    html, _result, _panels = page
    ids = re.findall(r' id="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    assert html.count('role="tabpanel"') == 9


def test_every_alert_anchor_exists(page) -> None:
    html, _result, _panels = page
    payload = json.loads(
        re.search(r'<script type="application/json" id="pv-data">(.*?)</script>', html, re.S).group(1)
    )
    for finding in payload["findings"]:
        anchor = finding["anchor"]
        if anchor:
            assert f'id="pv-card-{anchor}"' in html


def test_each_card_has_four_explanation_fields(page) -> None:
    html, _result, _panels = page
    explains = re.findall(r'<dl class="pv-explain">(.*?)</dl>', html, re.S)
    assert len(explains) == 12
    for block in explains:
        assert block.count("<dt ") == 4
        assert block.count("<dd ") == 4
        for value in re.findall(r"<dd [^>]*>(.*?)</dd>", block, re.S):
            assert value.strip()


def test_drawer_template_for_every_chart(page) -> None:
    html, _result, _panels = page
    assert len(re.findall(r'<template id="pv-tpl-', html)) == 12
    assert len(re.findall(r'class="pv-card"', html)) == 12


def test_not_measured_never_renders_zero(page) -> None:
    html, _result, _panels = page
    assert not re.search(r'data-state="not-measured"[^>]*>\s*0', html)
    assert "not measured" in html


def test_no_external_requests(page) -> None:
    html, _result, _panels = page
    assert "http://" not in html
    assert "https://" not in html
    assert "<link" not in html
    assert "@import" not in html
    assert 'src="//' not in html


def test_alt_text_parity_for_svg(page) -> None:
    html, _result, _panels = page
    svgs = re.findall(r'<svg [^>]*role="img"', html)
    titles = re.findall(r"<title id=\"[^\"]+\">(.*?)</title>", html, re.S)
    assert len(svgs) == len(titles)
    assert titles
    assert all(title.strip() for title in titles)


def test_alt_text_parity_for_images(page) -> None:
    html, _result, _panels = page
    images = re.findall(r"<img\b", html)
    alts = re.findall(r"\balt=\"([^\"]+)\"", html)
    assert len(images) == len(alts)


def test_second_series_has_pattern(page) -> None:
    html, _result, _panels = page
    assert 'id="pv-hatch-b"' in html
    assert 'url(#pv-hatch-b)' in html


def test_token_contrast_meets_aa() -> None:
    from plantvision.analytics.dashboard.tokens import contrast_ratio

    bg = "#2E2952"
    for colour in ("#D6D1EC", "#A9A2CC", "#FBC490", "#FFFFFF", "#2FE3A7"):
        assert contrast_ratio(colour, bg) >= 4.5


def test_embedded_payload_parses(page) -> None:
    html, result, _panels = page
    block = re.search(
        r'<script type="application/json" id="pv-data">(.*?)</script>', html, re.S
    )
    assert block is not None
    payload = json.loads(block.group(1).replace("<\\/", "</"))
    assert payload["schema"] == "pv-dashboard/2"
    assert payload["totals"]["panels"] == 3
    assert len(payload["cards"]) == 12
    assert payload["now_source"] == "cli"
    assert result.rows_total == 24


def test_reduced_motion_and_tier_css_present(page) -> None:
    html, _result, _panels = page
    assert "prefers-reduced-motion" in html
    assert "dataset.tier" in html
    assert "localStorage" in html


def test_page_is_deterministic_for_fixed_now(tmp_path: Path) -> None:
    panels = _panels(tmp_path)
    first = tmp_path / "a.html"
    second = tmp_path / "b.html"
    build_report(panels, first, now=NOW, title="T", include_frames=False)
    build_report(panels, second, now=NOW, title="T", include_frames=False)
    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(
        second.read_bytes()
    ).hexdigest()


def test_language_dicts_have_identical_keys() -> None:
    assert set(TEXTS["en"]) == set(TEXTS["ru"])
    for lang in ("en", "ru"):
        for key, value in TEXTS[lang].items():
            assert value.strip(), f"{lang}:{key}"


def test_every_rendered_card_has_both_languages(page) -> None:
    html, _result, _panels = page
    assert 'data-en=""' not in html
    assert 'data-ru=""' not in html
    assert html.count("data-en=") == html.count("data-ru=")
    for card_id in (
        "ch-ov-kpi-rings",
        "ch-ov-frames-bars",
        "ch-ov-status-board",
        "ch-ov-severity-donut",
        "ch-ov-coverage-strips",
        "ch-gr-area-px",
        "ch-gr-area-cm2",
        "ch-gr-rate-bars",
        "ch-gr-daily-bars",
        "ch-gr-daily-table",
    ):
        markup = _card_markup(html, card_id)
        assert markup.count("data-en=") >= 11
        assert markup.count("data-ru=") >= 11


def test_language_toggle_and_html_lang(page) -> None:
    html, _result, _panels = page
    assert 'id="pv-lang"' in html
    assert re.search(r'<html lang="en">', html)
    assert 'data-en="RU"' in html
    assert 'data-ru="EN"' in html


def test_russian_build_uses_ru_html_lang(tmp_path: Path) -> None:
    panels = _panels(tmp_path)
    out = tmp_path / "ru.html"
    build_report(panels, out, now=NOW, title="T", include_frames=False, lang="ru")
    html = out.read_text(encoding="utf-8")
    assert re.search(r'<html lang="ru">', html)
    assert 'data-lang="ru"' in html
    assert "Обзор" in html
    assert "Рост" in html


RAIL_LABELS = {
    "en": [
        "Overview",
        "Crops",
        "Growth",
        "Shape",
        "Quality",
        "Alerts",
        "Compare",
        "Capture",
        "Method",
    ],
    "ru": [
        "Обзор",
        "Культуры",
        "Рост",
        "Форма",
        "Качество",
        "Алерты",
        "Сравнение",
        "Съёмка",
        "Метод",
    ],
}


def test_rail_labels_are_short_and_titled(tmp_path: Path) -> None:
    panels = _panels(tmp_path)
    for lang, expected in RAIL_LABELS.items():
        out = tmp_path / f"rail-{lang}.html"
        build_report(
            panels, out, now=NOW, title="T", include_frames=False, lang=lang
        )
        html = out.read_text(encoding="utf-8")
        rail = re.search(r'<aside class="pv-rail".*?</aside>', html, re.S)
        assert rail is not None
        markup = rail.group(0)
        labels = re.findall(
            r'<span class="pv-rail-lbl"[^>]*>(.*?)</span>', markup, re.S
        )
        assert labels == expected
        assert all(len(label) <= 9 for label in labels), (lang, labels)
        buttons = re.findall(r"<button [^>]*role=\"tab\"[^>]*>", markup)
        assert len(buttons) == 9
        assert all(re.search(r'\btitle="[^"]+"', button) for button in buttons)
        assert all(re.search(r'\baria-label="[^"]+"', button) for button in buttons)


def test_overview_conclusion_names_the_freshness_budget() -> None:
    for key in ("ch-ov-kpi-rings.conclusion", "ch-ov-status-board.conclusion"):
        assert "freshness budget" in TEXTS["en"][key]
        assert "бюджет свежести" in TEXTS["ru"][key]


def test_gate_one_shell_has_seven_coming_soon_tabs(page) -> None:
    html, _result, _panels = page
    assert html.count('class="pv-empty pv-coming"') == 7
    assert len(re.findall(r'<button [^>]*role="tab" [^>]*data-tab=', html)) == 9


def test_grid_data_cols_matches_visible_card_count(page) -> None:
    html, _result, _panels = page
    cols = re.findall(r'<div class="pv-grid" data-cols="(\d+)">', html)
    assert cols == ["3", "2", "1", "1", "1", "2"]


def test_card_span_is_clamped_to_grid_columns(page) -> None:
    html, _result, _panels = page
    rings = _card_markup(html, "ch-ov-kpi-rings")
    board = _card_markup(html, "ch-ov-status-board")
    single = _card_markup(html, "ch-gr-area-px")
    assert 'data-span="2"' in rings
    assert 'data-span="3"' in board
    # A one-card subpanel has one grid column, so its span clamps to 1.
    assert 'data-span="1"' in single


def test_no_inline_grid_column_in_markup(page) -> None:
    html, _result, _panels = page
    assert 'style="grid-column:span' not in html
    assert not re.search(r'style="[^"]*grid-column', html)


def test_every_emitted_span_is_valid(page) -> None:
    html, _result, _panels = page
    spans = re.findall(r'<article class="pv-card"[^>]*data-span="(\d+)"', html)
    assert spans
    assert set(spans) <= {"1", "2", "3"}


def test_mobile_span_reset_wins_over_tablet_rule() -> None:
    tablet_at = CSS.index("@media (max-width:1199px)")
    mobile_at = CSS.index("@media (max-width:899px)")
    assert tablet_at < mobile_at
    tablet = CSS[tablet_at:mobile_at]
    mobile = CSS[mobile_at:]
    assert '.pv-grid>.pv-card[data-span="3"]{grid-column:span 2!important}' in tablet
    assert '.pv-grid>.pv-card[data-span="2"]' in tablet
    assert ".pv-grid>.pv-card[data-span]{grid-column:span 1!important}" in mobile
    assert "grid-auto-columns:0" in CSS
    assert "overflow-x:clip" in CSS


def test_drawer_axes_emit_the_real_unit(page) -> None:
    html, _result, _panels = page
    payload = json.loads(
        re.search(
            r'<script type="application/json" id="pv-data">(.*?)</script>', html, re.S
        ).group(1)
    )
    cards = {card["id"]: card for card in payload["cards"]}
    assert cards["ch-ov-frames-bars"]["axes"]["y_en"] == "count"
    assert cards["ch-gr-area-px"]["axes"]["y_en"] == "px"
    assert cards["ch-gr-area-cm2"]["axes"]["y_en"] == "cm²"
    assert cards["ch-gr-daily-bars"]["axes"]["y_en"] == "px"
    assert cards["ch-gr-rate-bars"]["axes"]["y_en"] == "%"


def test_no_crop_or_method_literals_in_src() -> None:
    root = Path(__file__).resolve().parent.parent / "src" / "plantvision" / "analytics" / "dashboard"
    pattern = re.compile(r"basil|lettuce|phone|sam2|exg", re.I)
    for path in sorted(root.rglob("*.py")):
        assert not pattern.search(path.read_text(encoding="utf-8")), path


def test_controls_markup(page) -> None:
    html, _result, _panels = page
    assert 'class="pv-controls"' in html
    for control in ("pv-f-crop", "pv-f-window", "pv-f-agg", "pv-f-mode"):
        assert f'id="{control}"' in html
    assert 'id="pv-crop-pop"' in html
    assert 'id="pv-filter-note"' in html


def test_snapshot_dialog_markup(page) -> None:
    html, _result, _panels = page
    assert 'id="pv-snap"' in html
    assert 'id="pv-snap-text"' in html
    assert 'id="pv-snap-a"' in html and 'id="pv-snap-b"' in html
    assert 'id="pv-snap-table"' in html
    assert html.count("data-snap-tab=") == 2
    assert "data-snap-close>Close</button>" in html


def test_last_frames_card_images(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parent.parent
    panels = load_panels(root / "configs" / "dashboard-panels.yaml")
    out = tmp_path / "frames.html"
    build_report(panels, out, now=NOW, title="Frames", include_frames=True)
    html = out.read_text(encoding="utf-8")
    assert html.count('class="pv-frame"') == 3
    assert len(re.findall(r"<img\b", html)) == len(re.findall(r'\balt="', html))
