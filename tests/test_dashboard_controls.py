"""Contract tests for controls, the client renderer and result snapshots."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from plantvision.analytics.dashboard import charts, contract, layout
from plantvision.analytics.dashboard.build import build_report, load_panels
from plantvision.analytics.dashboard.copy import (
    TEXTS,
    cards_for_payload,
    join_fragments,
)
from plantvision.analytics.dashboard.svg import linear
from plantvision.analytics.dashboard.model import (
    build_payload,
    last_frame_block,
    panel_payload,
    points_table,
    trailing_index_series,
)

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def _row(**values: str) -> dict[str, str]:
    """One CSV-like row with defaults."""
    row = {
        "captured_at": "",
        "area_px": "",
        "area_cm2": "",
        "scale_ok": "",
        "quality_flag": "",
        "settings_source": "",
    }
    row.update(values)
    return row


@pytest.fixture(scope="module")
def payload() -> dict[str, object]:
    """The real configured payload with cards filled."""
    panels = load_panels(ROOT / "configs" / "dashboard-panels.yaml")
    data = build_payload(panels, now=NOW, title="Test dashboard")
    data["frames"] = []
    data["cards"] = cards_for_payload(data)
    return data


@pytest.fixture(scope="module")
def doc(tmp_path_factory: pytest.TempPathFactory) -> str:
    """One real self-contained document."""
    root = tmp_path_factory.mktemp("controls-doc")
    out = root / "index.html"
    build_report(
        load_panels(ROOT / "configs" / "dashboard-panels.yaml"),
        out,
        now=NOW,
        title="Test dashboard",
        include_frames=False,
    )
    return out.read_text(encoding="utf-8")


def test_contract_matches_chart_constants() -> None:
    assert contract.RENDER["pl"] == charts.PAD_L
    assert contract.RENDER["pt"] == charts.PAD_T
    assert contract.RENDER["pr"] == charts.PAD_R
    assert contract.RENDER["pb"] == charts.PAD_B
    assert contract.RENDER["pw"] == charts.PLOT_W
    assert contract.RENDER["ph"] == charts.PLOT_H
    assert contract.RENDER["legendY"] == charts.LEGEND_Y
    assert contract.RENDER["xLabelY"] == charts.X_LABEL_Y
    assert contract.RENDER["xTitleY"] == charts.X_TITLE_Y


def test_points_table_columnar_shape() -> None:
    rows = [
        _row(captured_at="2026-10-24T05:48:26Z", area_px="10", area_cm2="1.5"),
        _row(captured_at="2026-10-24T05:53:26Z", area_px="20", area_cm2="2.5"),
    ]
    table = points_table(rows)
    assert set(table) == {"ts", "area_px", "area_cm2"}
    assert len(table["ts"]) == len(table["area_px"]) == len(table["area_cm2"]) == 2


def test_points_table_keeps_nulls() -> None:
    rows = [
        _row(captured_at="2026-10-24T05:48:26Z", area_px="0", area_cm2=""),
        _row(captured_at="2026-10-24T05:53:26Z", area_px="", area_cm2="3.0"),
    ]
    table = points_table(rows)
    assert table["area_px"] == [0.0, None]
    assert table["area_cm2"] == [None, 3.0]


def test_points_table_skips_undated_rows() -> None:
    rows = [
        _row(captured_at="", area_px="10"),
        _row(captured_at="not-a-date", area_px="20"),
        _row(captured_at="2026-10-24T05:48:26Z", area_px="30"),
    ]
    assert points_table(rows)["ts"] == [1792820906000]


def test_last_frame_block_single_row() -> None:
    block = last_frame_block([_row(captured_at="2026-10-24T05:48:26Z", area_px="10")])
    assert block["value"] == 10.0
    assert block["prev"] is None
    assert block["delta"] is None
    assert block["delta_pct"] is None


def test_last_frame_block_delta_pct() -> None:
    block = last_frame_block(
        [
            _row(captured_at="2026-10-24T05:48:26Z", area_px="100"),
            _row(captured_at="2026-10-24T05:53:26Z", area_px="125"),
        ]
    )
    assert block["prev"] == 100.0
    assert block["delta"] == 25.0
    assert block["delta_pct"] == 25.0


def test_trailing_index_starts_at_100() -> None:
    rows = [
        _row(captured_at=f"2026-10-24T05:{index:02d}:00Z", area_px=str(100 + index))
        for index in range(30)
    ]
    series = trailing_index_series(rows, count=10)
    assert len(series) == 10
    assert series[0][1] == 100.0


def test_trailing_index_rejects_zero_base() -> None:
    rows = [_row(captured_at="2026-10-24T05:48:26Z", area_px="0")]
    assert trailing_index_series(rows) == []


def test_crops_payload_order_and_counts() -> None:
    panels = [
        {"id": "p1", "crop": "alpha", "rows": 10, "last_at": "2026-10-24T05:48:26Z"},
        {"id": "p2", "crop": "beta", "rows": 20, "last_at": "2026-10-25T05:48:26Z"},
        {"id": "p3", "crop": "alpha", "rows": 5, "last_at": "2026-10-26T05:48:26Z"},
    ]
    crops = contract.crops_payload(panels)
    assert [crop["name"] for crop in crops] == ["alpha", "beta"]
    assert crops[0]["rows"] == 15
    assert crops[0]["panels"] == ["p1", "p3"]
    assert crops[0]["last_at"] == "2026-10-26T05:48:26Z"


def test_cards_declare_filter_scope(payload) -> None:
    cards = payload["cards"]
    assert len(cards) == 12
    for card in cards:
        block = card["filter"]
        assert block["crop"] in {"full", "hide", "all-panels"}
        for key in ("window", "agg", "mode"):
            assert block[key] in {"full", "hide", "n/a"}
    client = {card["id"] for card in cards if card["render"] == "client"}
    assert client == {
        "ch-gr-area-px",
        "ch-gr-area-cm2",
        "ch-gr-rate-bars",
        "ch-gr-daily-bars",
        "ch-gr-daily-table",
    }


def test_renderer_enums_match_contract(payload) -> None:
    filters = payload["filters"]
    for key, values in contract.FILTERS.items():
        assert tuple(filters[key]) == values


def test_renderer_js_budget() -> None:
    # Batch 1.6 moves the snapshot diff into the client renderer; the binding
    # constraint is the 700 KB page gate, this cap only trips on real bloat.
    assert len(layout.JS_FILTER) <= 45_000
    assert len(layout.JS) <= 65_000


def test_renderer_constants_in_js() -> None:
    for key, value in contract.RENDER.items():
        assert f"{key}:{value}" in layout.JS_FILTER


def test_renderer_has_no_curve_command() -> None:
    body = layout.JS_FILTER.lower()
    assert "curve" not in body
    assert '"C"' not in layout.JS_FILTER
    assert '"Q"' not in layout.JS_FILTER


def test_controls_markup_ids(doc: str) -> None:
    for control in (
        "pv-f-crop",
        "pv-f-window",
        "pv-f-agg",
        "pv-f-mode",
        "pv-f-reset",
        "pv-f-snap",
        "pv-crop-pop",
    ):
        assert f'id="{control}"' in doc


def test_control_css_classes_present() -> None:
    for name in (".pv-ctl", ".pv-pop", ".pv-snap", ".pv-fresh", ".pv-controls"):
        assert name in layout.CONTROL_CSS


def test_crop_popover_wrapper_is_positioned_relative() -> None:
    css = layout.CONTROL_CSS
    assert ".pv-pop-wrap{position:relative" in css
    assert "top:calc(100% + 6px);left:0" in css


def test_crop_popover_list_scrolls() -> None:
    assert (
        ".pv-pop-list{max-height:min(60vh, 420px);overflow:auto}"
        in layout.CONTROL_CSS
    )


def test_crop_popover_clamps_to_viewport() -> None:
    js = layout.JS_FILTER
    assert "r.right>window.innerWidth-8" in js
    assert 'pop.style.left="auto"' in js
    assert 'pop.style.right="0"' in js


def test_crop_popover_dismisses_on_outside_pointerdown() -> None:
    js = layout.JS_FILTER
    marker = 'document.addEventListener("pointerdown"'
    assert marker in js
    handler = js.split(marker, 1)[1][:700]
    assert "pop.contains(t)" in handler
    assert "cb.contains(t)" in handler
    assert "closeCropPop()" in handler


def test_crop_done_button_exists_in_both_languages(payload) -> None:
    assert TEXTS["en"]["ui.controls.done"] == "Done"
    assert TEXTS["ru"]["ui.controls.done"] == "Готово"
    english = layout.controls(payload, "en")
    russian = layout.controls(payload, "ru")
    assert 'id="pv-crop-done"' in english
    assert 'id="pv-crop-done"' in russian
    assert 'data-en="Done"' in english and 'data-ru="Готово"' in english
    assert ">Done</button>" in english
    assert ">Готово</button>" in russian


def test_crop_popover_dialog_role_and_label(doc: str) -> None:
    match = re.search(r'<div id="pv-crop-pop".*?>', doc)
    assert match is not None
    tag = match.group(0)
    assert 'role="dialog"' in tag
    assert 'aria-label="crop"' in tag
    assert 'aria-haspopup="true"' in doc


def test_new_ui_keys_present_in_both_langs() -> None:
    prefixes = ("ui.controls.", "ui.filter.", "ui.fresh.", "ui.snap.", "ui.ov.")
    added = {
        key
        for key in TEXTS["en"]
        if key.startswith(prefixes) and key not in _BASELINE_UI
    }
    assert added
    for key in added:
        assert key in TEXTS["ru"]


_BASELINE_UI = {
    "ui.skip",
    "ui.open",
    "ui.close",
    "ui.lang",
    "ui.asof",
    "ui.generated",
    "ui.verdict",
}


def test_filter_grammar_documented() -> None:
    docs = (ROOT / "docs" / "DASHBOARD.md").read_text(encoding="utf-8")
    examples = (
        "#/overview",
        "#/growth/area-cm2!c=basil,lettuce&w=7d&a=hourly&m=idx",
        "#/growth/area-cm2~ch-gr-area-cm2!c=basil,lettuce&w=7d&a=hourly&m=idx",
        "#/crops/lettuce-farm03-exg",
        "#/alerts!c=lettuce",
    )
    for example in examples:
        assert example in docs


def test_crop_literals_absent_from_src(payload) -> None:
    names = [str(crop["name"]) for crop in payload["crops"]]
    root = ROOT / "src" / "plantvision" / "analytics" / "dashboard"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for name in names:
        assert name not in text


def test_snapshot_schema_keys_in_js() -> None:
    for key in (
        "schema",
        "generated_at",
        "now_source",
        "page",
        "filters",
        "window",
        "panels",
        "cards",
        "sources",
        "thumbnails",
    ):
        assert key in layout.JS_FILTER


_NODE = shutil.which("node")


def _stable_js() -> str:
    """The client-side key-sorting serialiser, extracted from the renderer."""
    js = layout.JS
    start = js.index("function stable(v,lvl){")
    end = js.index("function flat(", start)
    return js[start:end]


@pytest.mark.skipif(_NODE is None, reason="node is required to run renderer JS")
def test_snapshot_export_is_indented_and_deterministic() -> None:
    """S1: exports are pretty-printed and byte-identical for one state."""
    sample = {"z": None, "a": [3, {"d": 4, "c": 5}], "b": 1}
    driver = (
        _stable_js()
        + "\nvar a=stable("
        + json.dumps(sample)
        + ");"
        + "\nvar b=stable({b:1,a:[3,{c:5,d:4}],z:null});"
        + "\nprocess.stdout.write(JSON.stringify({text:a,same:a===b}));"
    )
    result = subprocess.run(
        [_NODE, "-e", driver],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    exported = json.loads(result.stdout)
    assert exported["text"].startswith("{\n")
    assert exported["text"] == json.dumps(sample, indent=2, sort_keys=True)
    assert exported["same"] is True


def test_snapshot_cards_reuse_the_filter_aware_join() -> None:
    """S2: snapshot copy goes through the same joiner as the on-screen cards."""
    js = layout.JS_FILTER
    build = js[js.index("function buildSnap()") : js.index("function exportSnap()")]
    assert 'joinField(c,"now",ps,allPanels)' in build
    assert 'joinField(c,"conclusion",ps,allPanels)' in build


def test_snapshot_close_label_is_short() -> None:
    """S3: the dialog close control reads Close / Закрыть."""
    assert TEXTS["en"]["ui.snap.close"] == "Close"
    assert TEXTS["ru"]["ui.snap.close"] == "Закрыть"


def _growth_card(payload, card_id: str = "ch-gr-area-px") -> dict[str, object]:
    """One growth card record from the payload."""
    return next(card for card in payload["cards"] if card["id"] == card_id)


def _panel_ids(payload) -> list[str]:
    """Panel ids in config order."""
    return [str(panel["id"]) for panel in payload["panels"]]


def test_filter_fragments_are_keyed_by_panel(payload) -> None:
    ids = set(_panel_ids(payload))
    for card in payload["cards"]:
        if card["id"] not in {
            "ch-gr-area-px",
            "ch-gr-area-cm2",
            "ch-gr-rate-bars",
            "ch-gr-daily-bars",
            "ch-gr-daily-table",
        }:
            continue
        assert set(card["now_parts"]) == ids
        assert set(card["conclusion_parts"]) == ids
        for parts in (card["now_parts"], card["conclusion_parts"]):
            for text in parts.values():
                assert text["en"].strip()
                assert text["ru"].strip()


def test_single_crop_copy_names_only_that_panel(payload) -> None:
    card = _growth_card(payload)
    panel = payload["panels"][0]
    now = join_fragments(card, "now", [str(panel["id"])], "en")
    conclusion = join_fragments(card, "conclusion", [str(panel["id"])], "en")
    assert str(panel["label"]) in now
    assert str(panel["label"]) in conclusion
    for other in payload["panels"][1:]:
        assert str(other["label"]) not in now
        assert str(other["label"]) not in conclusion


def test_single_crop_conclusion_differs_from_now(payload) -> None:
    """P1: a one-crop conclusion is a summary, not a repeat of ``now``."""
    for card in payload["cards"]:
        if not card["now_parts"]:
            continue
        for panel in payload["panels"]:
            panel_id = str(panel["id"])
            for lang in ("en", "ru"):
                now = join_fragments(card, "now", [panel_id], lang)
                conclusion = join_fragments(card, "conclusion", [panel_id], lang)
                assert now != conclusion, (card["id"], panel_id, lang)


def test_two_crop_copy_names_both_panels(payload) -> None:
    card = _growth_card(payload)
    ids = _panel_ids(payload)[:2]
    now = join_fragments(card, "now", ids, "en")
    for panel in payload["panels"][:2]:
        assert str(panel["label"]) in now
    assert str(payload["panels"][2]["label"]) not in now
    for lang in ("en", "ru"):
        assert (
            join_fragments(card, "conclusion", ids, lang)
            == card[f"conclusion_{lang}"]
        )


def test_all_crops_copy_matches_precomputed_string(payload) -> None:
    card = _growth_card(payload)
    ids = _panel_ids(payload)
    for field in ("now", "conclusion"):
        assert join_fragments(card, field, ids, "en") == card[f"{field}_en"]
        assert join_fragments(card, field, ids, "ru") == card[f"{field}_ru"]


def test_filter_aware_do_line_rules(payload) -> None:
    card = _growth_card(payload)
    assert card["do_ok"]["en"].strip()
    assert card["do_ok"]["ru"].strip()
    critical = [
        panel for panel in payload["panels"] if panel.get("verdict") == "critical"
    ]
    assert critical
    for panel in critical:
        assert card["do_actions"][str(panel["id"])]["en"].strip()


def test_topbar_drops_panel_freshness_chips(doc: str) -> None:
    header = re.search(
        r'<header class="pv-topbar">.*?</header>', doc, re.S
    )
    assert header is not None
    assert "pv-fresh" not in header.group(0)


def test_adaptive_time_axis_and_parity_features_in_js() -> None:
    assert "sp<=3*D" in layout.JS
    assert "sp<=30*D" in layout.JS
    js = layout.JS_FILTER
    assert "lastLab" in js and "continue" in js
    assert "captured_at (UTC)" in js
    assert "pv-ax-title" in js
    assert "scale_missing" in js
    assert "nearestDistance" in layout.JS


def test_payload_timestamps_use_z_suffix(payload) -> None:
    assert str(payload["now"]).endswith("Z")
    assert str(payload["generated_at"]).endswith("Z")
    assert "+00:00" not in str(payload["now"])


def test_client_geometry_matches_python_renderer_by_one_px() -> None:
    x_domain = (0.0, 1000.0)
    y_domain = (0.0, 10.0)
    py_x = linear(x_domain, (charts.PAD_L, charts.PAD_L + charts.PLOT_W))
    js_x = linear(
        x_domain,
        (contract.RENDER["pl"], contract.RENDER["pl"] + contract.RENDER["pw"]),
    )
    py_y = linear(
        y_domain, (charts.PAD_T + charts.PLOT_H, charts.PAD_T)
    )
    js_y = linear(
        y_domain,
        (contract.RENDER["pt"] + contract.RENDER["ph"], contract.RENDER["pt"]),
    )
    for value in (0.0, 1.0, 250.0, 999.0):
        assert abs(py_x(value) - js_x(value)) <= 1.0
    for value in (0.0, 5.0, 10.0):
        assert abs(py_y(value) - js_y(value)) <= 1.0
    markup = charts.line_chart(
        charts.ChartSpec(chart_id="ch-parity", title="Parity", desc="Parity"),
        [charts.PlotSeries("A", [[(0, 1.0), (1000, 9.0)]])],
    )
    cx = float(re.search(r'<circle cx="([\d.]+)"', markup).group(1))
    assert abs(cx - js_x(0.0)) <= 1.0
