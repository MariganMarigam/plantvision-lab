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
from plantvision.analytics.dashboard.copy import cards_for_payload, join_fragments
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


def test_client_reads_ring_values_instead_of_recomputing() -> None:
    js = layout.JS
    assert "overview" in js and "ring_sets" in js
    body = js[js.index("function renderRings()") : js.index("function renderBoard()")]
    assert "3*critical" not in body and "3 * critical" not in body
    assert "ringStroke" in body


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


def test_aggregate_chip_is_not_created_for_subsets() -> None:
    js = layout.JS
    body = js[js.index("function visibility()") : js.index("function cap(card")]
    assert "ui.filter.aggregate" not in body


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
