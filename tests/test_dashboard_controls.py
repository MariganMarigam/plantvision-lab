"""Contract tests for controls, the client renderer and result snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from plantvision.analytics.dashboard import charts, contract, layout
from plantvision.analytics.dashboard.build import build_report, load_panels
from plantvision.analytics.dashboard.copy import TEXTS, cards_for_payload
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
    assert len(layout.JS_FILTER) <= 24_000
    assert len(layout.JS) <= 40_000


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
