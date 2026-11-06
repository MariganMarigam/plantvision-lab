"""Batch 1.6: filtered Overview rings/board/bars and the visual snapshot diff."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from plantvision.analytics.dashboard import build, layout
from plantvision.analytics.dashboard.build import build_report, load_panels
from plantvision.analytics.dashboard.copy import TEXTS, cards_for_payload, join_fragments
from plantvision.analytics.dashboard.model import build_payload

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
_NODE = shutil.which("node")

_OVERVIEW_CARDS = {
    "ch-ov-kpi-rings",
    "ch-ov-frames-bars",
    "ch-ov-status-board",
}


@pytest.fixture(scope="module")
def panels():
    """The real configured panel list."""
    return load_panels(ROOT / "configs" / "dashboard-panels.yaml")


@pytest.fixture(scope="module")
def payload(panels):
    """The real payload with cards filled and ring sets attached."""
    data = build_payload(panels, now=NOW, title="Test dashboard")
    data["frames"] = []
    data["overview"] = {"ring_sets": build.ring_sets(data["panels"])}
    data["cards"] = cards_for_payload(data)
    return data


@pytest.fixture(scope="module")
def doc(panels, tmp_path_factory: pytest.TempPathFactory) -> str:
    """One real self-contained document."""
    out = tmp_path_factory.mktemp("b16-doc") / "index.html"
    build_report(panels, out, now=NOW, title="Test dashboard", include_frames=False)
    return out.read_text(encoding="utf-8")


def _card_markup(html: str, card_id: str) -> str:
    start = html.index(f'id="pv-card-{card_id}"')
    return html[start : html.index("</article>", start)]


def _snap(**overrides):
    """One minimal ``pv-snapshot/1`` object for the diff model."""
    snap = {
        "schema": "pv-snapshot/1",
        "generated_at": "2026-11-03T12:00:00Z",
        "now_source": "cli",
        "page": {"build": "pv-dashboard/2", "lang": "en", "renderer": "client"},
        "filters": {
            "crops": ["basil", "lettuce"],
            "crop_state": "all",
            "window": "all",
            "window_label": "all",
            "aggregation": "raw",
            "mode": "abs",
        },
        "window": {
            "start_ms": 1792828106000,
            "end_ms": 1793653106000,
            "start": "2026-10-24T00:00:00Z",
            "end": "2026-11-03T00:00:00Z",
        },
        "panels": [
            {
                "id": "basil-farm02-sam2",
                "label": "basil farm-02 · SAM2",
                "crop": "basil",
                "method": "sam2",
                "rows": 681,
                "frames_in_window": 681,
                "state": "ok",
                "kpi": {"scale_pct": 99.4, "freshness_pct": 2.3, "shape_pct": 100.0},
                "alerts": {"critical": 0, "warn": 2},
                "series": {
                    "area_px": {
                        "unit": "px",
                        "points": [
                            ["2026-10-24T05:00:00Z", 200000],
                            ["2026-10-25T05:00:00Z", 210000],
                        ],
                        "stats": {"last": 210000.0, "first": 200000.0},
                    },
                    "area_cm2": {"unit": "cm²", "points": [], "stats": None},
                },
            },
            {
                "id": "lettuce-farm03-exg",
                "label": "lettuce farm-03 · ExG",
                "crop": "lettuce",
                "method": "exg",
                "rows": 400,
                "frames_in_window": 400,
                "state": "ok",
                "kpi": {"scale_pct": 80.0, "freshness_pct": 10.0, "shape_pct": 50.0},
                "alerts": {"critical": 1, "warn": 0},
                "series": {
                    "area_px": {
                        "unit": "px",
                        "points": [["2026-10-25T05:00:00Z", 90000]],
                        "stats": {"last": 90000.0, "first": 90000.0},
                    },
                    "area_cm2": {"unit": "cm²", "points": [], "stats": None},
                },
            },
        ],
        "findings": [
            {
                "panel": "basil-farm02-sam2",
                "rule_id": "stale-data",
                "severity": "warn",
                "value": 1.2,
                "threshold": 2.0,
            },
            {
                "panel": "lettuce-farm03-exg",
                "rule_id": "capture-gap",
                "severity": "critical",
                "value": 30.0,
                "threshold": 12.0,
            },
        ],
        "sources": [
            {
                "panel": "basil-farm02-sam2",
                "csv": "data/derived/metrics/basil-farm02-sam2.csv",
                "sha256_first": "aaa",
                "sha256_last": "bbb",
            },
            {
                "panel": "lettuce-farm03-exg",
                "csv": "data/derived/metrics/lettuce-timeseries.csv",
                "sha256_first": "ccc",
                "sha256_last": "ddd",
            },
        ],
        "thumbnails": [],
    }
    snap.update(overrides)
    return snap


def _run_diff(a: dict, b: dict) -> dict:
    """Run the client diff model under node and return its JSON output."""
    js = layout.JS
    start = js.index("/*pv-diff-begin*/")
    end = js.index("/*pv-diff-end*/") + len("/*pv-diff-end*/")
    driver = (
        js[start:end]
        + "\nvar out=snapDiff("
        + json.dumps(a)
        + ","
        + json.dumps(b)
        + ',function(k){return k;});'
        "\nprocess.stdout.write(JSON.stringify(out));"
    )
    result = subprocess.run(
        [_NODE, "-e", driver], check=True, capture_output=True, text=True, timeout=30
    )
    return json.loads(result.stdout)


# --- A1: ring sets ---------------------------------------------------------


def test_ring_sets_cover_every_non_empty_crop_subset(payload) -> None:
    sets = payload["overview"]["ring_sets"]
    ids = [str(panel["id"]) for panel in payload["panels"]]
    assert len(ids) == 3
    assert len(sets) == 2**len(ids) - 1 == 7
    assert "+".join(ids) in sets
    for value in sets.values():
        assert set(value) == {"scale", "freshness", "pressure", "shape"}


def test_ring_sets_all_panels_equals_current_aggregate(payload) -> None:
    ids = [str(panel["id"]) for panel in payload["panels"]]
    sets = payload["overview"]["ring_sets"]
    assert sets["+".join(ids)] == build.ring_values(payload["panels"])


def test_ring_sets_subset_matches_its_panels(payload) -> None:
    panels = payload["panels"]
    key = "+".join(str(panel["id"]) for panel in panels[:2])
    assert payload["overview"]["ring_sets"][key] == build.ring_values(panels[:2])


def _weighted_mean(panels, key: str) -> float:
    pairs = [
        (float(panel["kpi"][key]), int(panel["rows"]))
        for panel in panels
        if panel.get("kpi", {}).get(key) is not None
        and int(panel.get("rows", 0)) > 0
    ]
    return sum(value * weight for value, weight in pairs) / sum(
        weight for _value, weight in pairs
    )


def test_ring_scale_and_shape_are_true_weighted_means(payload) -> None:
    values = build.ring_values(payload["panels"])
    assert values["scale"] == pytest.approx(
        _weighted_mean(payload["panels"], "scale_pct")
    )
    assert values["shape"] == pytest.approx(
        _weighted_mean(payload["panels"], "shape_pct")
    )
    assert values["shape"] == pytest.approx(100.0)
    assert values["scale"] < 100.0


def test_single_crop_scale_matches_its_panel_percentage(payload) -> None:
    by_crop = {str(panel["crop"]): panel for panel in payload["panels"]}
    expected = {"lettuce": 61.21, "basil": 99.41, "phone capture": 60.87}
    for crop, value in expected.items():
        assert build.ring_values([by_crop[crop]])["scale"] == pytest.approx(value)
    assert build.ring_values([by_crop["phone capture"]])["shape"] is None


def test_two_crop_scale_is_the_weighted_mean_of_both(payload) -> None:
    by_crop = {str(panel["crop"]): panel for panel in payload["panels"]}
    subset = [by_crop["basil"], by_crop["lettuce"]]
    values = build.ring_values(subset)
    assert values["scale"] == pytest.approx(_weighted_mean(subset, "scale_pct"))
    assert 61.21 < values["scale"] < 99.41


def test_client_reads_ring_values_instead_of_recomputing() -> None:
    js = layout.JS
    assert "overview" in js and "ring_sets" in js
    body = js[js.index("function renderRings()") : js.index("function renderBoard()")]
    assert "3*critical" not in body and "3 * critical" not in body
    assert "ringStroke" in body


@pytest.mark.skipif(_NODE is None, reason="node is required to run renderer JS")
def test_ring_centre_text_uses_one_decimal_only_when_needed() -> None:
    js = layout.JS
    body = js[js.index("function ringPct") : js.index("function renderRings")]
    driver = (
        body
        + "\nprocess.stdout.write(JSON.stringify([ringPct(100),ringPct(79.5),"
        "ringPct(61.21),ringPct(0)]));"
    )
    result = subprocess.run(
        [_NODE, "-e", driver], check=True, capture_output=True, text=True, timeout=30
    )
    assert json.loads(result.stdout) == ["100%", "79.5%", "61.2%", "0%"]


_AGGREGATE_CARD_IDS = (
    "ch-ov-severity-donut",
    "ch-ov-coverage-strips",
    "ch-ov-last-change",
    "ch-ov-last-frames",
)


def test_aggregate_cards_are_marked_for_the_all_panels_chip(doc: str) -> None:
    for card_id in _AGGREGATE_CARD_IDS:
        assert 'data-aggregate="1"' in _card_markup(doc, card_id), card_id


def test_aggregate_chip_copy_exists_in_both_languages() -> None:
    assert TEXTS["en"]["ui.filter.allPanels"] == "all panels"
    assert TEXTS["ru"]["ui.filter.allPanels"] == "все панели"
    body = layout.JS[
        layout.JS.index("function renderAggregateChips")
        : layout.JS.index("function thrCaption")
    ]
    assert "ui.filter.allPanels" in body
    assert 'setAttribute("title"' in body and 'setAttribute("aria-label"' in body


# --- A2: status board ------------------------------------------------------


@pytest.mark.skipif(_NODE is None, reason="node is required to run renderer JS")
def test_ring_stroke_follows_the_threshold_bands() -> None:
    js = layout.JS
    body = js[js.index("function ringStroke"): js.index("function renderBoard")]
    driver = (
        body
        + "\nprocess.stdout.write(JSON.stringify([ringStroke(90),ringStroke(89.9),"
        "ringStroke(50),ringStroke(49.9),ringStroke(0)]));"
    )
    result = subprocess.run(
        [_NODE, "-e", driver], check=True, capture_output=True, text=True, timeout=30
    )
    assert json.loads(result.stdout) == [
        "var(--pv-pos)",
        "#E0A800",
        "#E0A800",
        "url(#pv-grad-a)",
        "url(#pv-grad-a)",
    ]


def test_board_rows_carry_panel_ids_and_footer_count(doc: str) -> None:
    board = _card_markup(doc, "ch-ov-status-board")
    assert board.count("data-panel=") == 3
    assert "data-board-count" in board
    assert "data-board-empty" in board


def test_board_filters_rows_client_side() -> None:
    js = layout.JS
    body = js[js.index("function renderBoard()") : js.index("function renderFramesBars()")]
    assert "data-panel" in body
    assert "tr.hidden" in body or "row.hidden" in body
    assert "data-board-empty" in body


# --- A3: frames per day ----------------------------------------------------


def test_frames_bars_render_from_selected_panels() -> None:
    js = layout.JS
    body = js[
        js.index("function renderFramesBars()") : js.index("function renderOverview()")
    ]
    assert "pick()" in body
    assert ".daily" in body
    assert "G.pl" in body and "G.pt" in body


# --- A4: overview copy -----------------------------------------------------


def test_overview_cards_expose_per_panel_fragments(payload) -> None:
    ids = {str(panel["id"]) for panel in payload["panels"]}
    for card in payload["cards"]:
        if card["id"] not in _OVERVIEW_CARDS:
            continue
        assert set(card["now_parts"]) == ids, card["id"]
        assert set(card["conclusion_parts"]) == ids, card["id"]


def test_single_crop_overview_copy_names_only_that_panel(payload) -> None:
    basil = next(
        panel for panel in payload["panels"] if str(panel["crop"]) == "basil"
    )
    for card in payload["cards"]:
        if card["id"] != "ch-ov-kpi-rings":
            continue
        for field in ("now", "conclusion"):
            text = join_fragments(card, field, [str(basil["id"])], "en")
            assert str(basil["label"]) in text
            for other in payload["panels"]:
                if other is not basil:
                    assert str(other["label"]) not in text


def test_aggregate_chip_is_limited_to_a_crop_subset() -> None:
    js = layout.JS
    body = js[js.index("function renderAggregateChips") : js.index("function thrCaption")]
    assert 'data-aggregate="1"' in body
    assert "selected<total" in body
    assert "ui.filter.allPanels" in body


# --- A5: scope hint --------------------------------------------------------


def test_scope_hint_lists_the_four_filters(doc: str) -> None:
    labels = json.loads(
        doc[
            doc.index('id="pv-labels">') + len('id="pv-labels">') : doc.index(
                "</script>", doc.index('id="pv-labels">')
            )
        ]
    )
    keys = [entry["key"] for entry in labels["scope"]["keys"]]
    assert keys == ["crop", "window", "agg", "mode"]
    assert labels["scope"]["label"]["en"] == "Filters:"
    assert 'id="pv-scope"' in doc
    assert "renderScope" in layout.JS


def test_scope_hint_strikes_disabled_filters_per_tab(doc: str) -> None:
    labels = json.loads(
        doc[
            doc.index('id="pv-labels">') + len('id="pv-labels">') : doc.index(
                "</script>", doc.index('id="pv-labels">')
            )
        ]
    )
    assert labels["scope"]["off"]["alerts"] == ["window", "agg", "mode"]
    assert labels["scope"]["off"]["method"] == ["window", "agg", "mode"]
    assert "overview" not in labels["scope"]["off"]
    assert '"off"' in layout.JS or "'off'" in layout.JS


def test_scope_hint_reports_cards_that_stay_cross_panel(doc: str) -> None:
    labels = json.loads(
        doc[
            doc.index('id="pv-labels">') + len('id="pv-labels">') : doc.index(
                "</script>", doc.index('id="pv-labels">')
            )
        ]
    )
    assert (
        labels["terms"]["ui.scope.mixed"]["en"] == "some cards show all panels"
    )
    assert (
        labels["terms"]["ui.scope.mixed"]["ru"]
        == "часть карточек показывает все панели"
    )
    body = layout.JS[
        layout.JS.index("function renderScope") : layout.JS.index(
            "function updateCrumb"
        )
    ]
    assert "data-aggregate" in body and "ui.scope.mixed" in body


def test_scope_line_is_server_rendered_and_flagged_visible(doc: str) -> None:
    start = doc.index('<p class="pv-scope"')
    markup = doc[start : doc.index("</p>", start)]
    assert 'id="pv-scope"' in markup
    assert 'data-visible="1"' in markup
    assert "Filters:" in markup
    for name in ("crop", "window", "aggregation", "mode"):
        assert f">{name}<" in markup
    assert "pv-scope-note" in markup
    assert "some cards show all panels" in markup
    body = layout.JS[
        layout.JS.index("function renderScope") : layout.JS.index(
            "function updateCrumb"
        )
    ]
    assert 'setAttribute("data-visible", "1")' in body
    assert "el.hidden = false" in body


def test_scope_line_strikes_ignored_controls_per_tab() -> None:
    alerts = layout._scope_html("alerts", "en")
    assert alerts.count('class="off"') == 3
    assert "line-through" in layout.CSS


def test_single_panel_rings_copy_uses_singular_template(payload) -> None:
    lettuce = next(
        panel for panel in payload["panels"] if str(panel["crop"]) == "lettuce"
    )
    label = str(lettuce["label"])
    panel_id = str(lettuce["id"])
    card = next(
        card for card in payload["cards"] if card["id"] == "ch-ov-kpi-rings"
    )
    now = join_fragments(card, "now", [panel_id], "en")
    conclusion = join_fragments(card, "conclusion", [panel_id], "en")
    assert now == (
        f"{label}: scale coverage 61.2%; freshness 73.8%; shape coverage 100%."
    )
    assert conclusion == f"{label} is within the freshness budget."
    assert "1 panels" not in now + conclusion
    assert "0 of 1" not in now + conclusion


def test_single_panel_rings_conclusion_reports_age_outside_budget(payload) -> None:
    panel = next(
        panel for panel in payload["panels"] if str(panel["crop"]) == "lettuce"
    )
    stale = dict(panel, age_days=9.2)
    stale_payload = dict(payload, panels=[stale])
    card = next(
        card
        for card in cards_for_payload(stale_payload)
        if card["id"] == "ch-ov-kpi-rings"
    )
    text = join_fragments(card, "conclusion", [str(stale["id"])], "en")
    assert text == (
        f"{stale['label']} is outside the freshness budget "
        "(last frame 9.2 days old)."
    )


def test_single_panel_frames_copy_uses_singular_template(payload) -> None:
    lettuce = next(
        panel for panel in payload["panels"] if str(panel["crop"]) == "lettuce"
    )
    label = str(lettuce["label"])
    panel_id = str(lettuce["id"])
    card = next(
        card for card in payload["cards"] if card["id"] == "ch-ov-frames-bars"
    )
    now = join_fragments(card, "now", [panel_id], "en")
    conclusion = join_fragments(card, "conclusion", [panel_id], "en")
    assert now == (
        f"{label}: 843 frames across 1 panel; the busiest day is "
        "2026-10-29 with 191 frames."
    )
    assert conclusion == (
        f"{label}: 843 frames from one panel; the busiest day is "
        "2026-10-29 with 191 frames."
    )
    assert "1 panels" not in now + conclusion


def test_single_panel_russian_copy_is_singular(payload) -> None:
    lettuce = next(
        panel for panel in payload["panels"] if str(panel["crop"]) == "lettuce"
    )
    label = str(lettuce["label"])
    panel_id = str(lettuce["id"])
    rings = next(
        card for card in payload["cards"] if card["id"] == "ch-ov-kpi-rings"
    )
    frames = next(
        card for card in payload["cards"] if card["id"] == "ch-ov-frames-bars"
    )
    assert join_fragments(rings, "now", [panel_id], "ru") == (
        f"{label}: покрытие масштаба 61.2%; свежесть 73.8%; "
        "покрытие формы 100%."
    )
    assert join_fragments(rings, "conclusion", [panel_id], "ru") == (
        f"{label} в пределах бюджета свежести."
    )
    now = join_fragments(frames, "now", [panel_id], "ru")
    conclusion = join_fragments(frames, "conclusion", [panel_id], "ru")
    assert "1 панель" in now
    assert "с одной панели" in conclusion
    assert "1 панелям" not in now + conclusion


def test_rendered_fragments_never_repeat_a_panel_label(payload) -> None:
    for card in payload["cards"]:
        if not card["now_parts"]:
            continue
        for panel in payload["panels"]:
            label = str(panel["label"])
            panel_id = str(panel["id"])
            for field in ("now", "conclusion"):
                for lang in ("en", "ru"):
                    text = join_fragments(card, field, [panel_id], lang)
                    assert text.count(label) <= 1, (card["id"], field, lang, text)
                    assert "1 panels" not in text, (card["id"], field, lang)


# --- B: snapshot diff ------------------------------------------------------


def test_snapshot_export_carries_diff_inputs() -> None:
    js = layout.JS
    build_snap = js[js.index("function buildSnap()") : js.index("function exportSnap()")]
    assert "findings:" in build_snap
    assert "kpi:" in build_snap
    assert "alerts:" in build_snap


@pytest.mark.skipif(_NODE is None, reason="node is required to run renderer JS")
def test_diff_produces_kpi_panel_alert_source_groups() -> None:
    out = _run_diff(_snap(), _snap())
    assert set(out) >= {"header", "kpis", "panels", "alerts", "sources", "unchanged"}
    assert len(out["kpis"]) == 4
    assert [row["panel"] for row in out["panels"]] == [
        "basil-farm02-sam2",
        "lettuce-farm03-exg",
    ]
    assert out["alerts"] == []


@pytest.mark.skipif(_NODE is None, reason="node is required to run renderer JS")
def test_diff_detects_area_severity_and_hash_changes() -> None:
    after = _snap()
    after["panels"][0]["series"]["area_px"]["stats"]["last"] = 231000.0
    after["findings"][0]["severity"] = "critical"
    after["sources"][1]["sha256_last"] = "eee"
    out = _run_diff(_snap(), after)
    area = next(row for row in out["panels"] if row["panel"] == "basil-farm02-sam2")
    assert area["delta"] == pytest.approx(21000.0)
    assert area["delta_pct"] == pytest.approx(10.0)
    alerts = {row["key"]: row for row in out["alerts"]}
    assert alerts["basil-farm02-sam2|stale-data"]["change"] == "severity"
    sources = {row["panel"]: row for row in out["sources"]}
    assert sources["lettuce-farm03-exg"]["sha_changed"] is True
    assert sources["basil-farm02-sam2"]["sha_changed"] is False


@pytest.mark.skipif(_NODE is None, reason="node is required to run renderer JS")
def test_diff_collapses_unchanged_paths_to_a_count() -> None:
    out = _run_diff(_snap(), _snap())
    assert isinstance(out["unchanged"], int)
    assert out["unchanged"] > 0
    assert out["raw"] == []


def test_snapshot_export_stays_deterministic() -> None:
    js = layout.JS
    assert "stable(buildSnap())" in js
    assert "Math.random" not in js
    assert "Date.now" not in js


def test_raw_path_table_sits_behind_a_closed_toggle(doc: str) -> None:
    assert "<details" in doc and 'id="pv-snap-raw"' in doc
    segment = doc[doc.index('id="pv-snap-raw"') : doc.index("</details>")]
    assert "open" not in segment.split(">", 1)[0]
    assert 'id="pv-snap-table"' in segment
