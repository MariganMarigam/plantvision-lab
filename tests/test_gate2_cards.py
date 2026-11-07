"""B1 card, gating and page-acceptance tests for Crops + Data quality."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from plantvision.analytics.dashboard.build import Panel, build_report, load_panels
from plantvision.analytics.service import ServiceOptions, build_payload
from plantvision.analytics.service import derive, gate
from plantvision.analytics.validity import load_validity

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
CONFIG = ROOT / "configs" / "dashboard-panels.yaml"
B1_IDS = {
    "cd-identity",
    "cd-kpi-rings",
    "cd-area-line",
    "cd-light-compare",
    "cd-frame-thumb",
    "cd-coverage-table",
    "dq-scale-stacked",
    "dq-scale-ring",
    "dq-quality-bars",
    "dq-gap-bars",
    "dq-provenance-heatmap",
    "dq-coverage-table",
}


@pytest.fixture(scope="module")
def panels() -> list[Panel]:
    return load_panels(CONFIG, include_gate2=True)


@pytest.fixture(scope="module")
def payload(panels: list[Panel]) -> dict[str, object]:
    return build_payload(panels, NOW, ServiceOptions())


@pytest.fixture(scope="module")
def page(panels: list[Panel], tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("gate2-page")
    out = root / "index.html"
    result = build_report(panels, out, now=NOW, title="Gate 2", include_frames=False)
    return out.read_text(encoding="utf-8"), result


def test_b1_cards_registered(payload) -> None:
    ids = {str(card["id"]) for card in payload["cards"]}
    assert ids == B1_IDS
    assert len(payload["cards"]) == 33
    for card in payload["cards"]:
        assert card["primitive"] in {
            "table", "ring", "line", "small-multiples", "image",
            "stacked", "bars", "strips",
        }


def test_every_card_key_exists_in_payload(payload) -> None:
    for card in payload["cards"]:
        for read in card["reads"]:
            if read.startswith("tables."):
                assert read[len("tables."):] in payload["tables"], read
            elif read == "panels":
                assert payload["panels"]
            elif read == "conditions":
                assert payload["conditions"]["keys"]
            else:
                current = payload
                for part in read.split("."):
                    assert part in current, read
                    current = current[part]


def test_every_card_has_four_slots_bilingual(payload) -> None:
    for card in payload["cards"]:
        for slot in ("what", "how", "now", "do"):
            for lang in ("en", "ru"):
                assert str(card["slots"][f"{slot}_{lang}"]).strip()


def test_every_card_evidence_resolves(payload) -> None:
    for card in payload["cards"]:
        for evidence_id in card["evidence"]:
            assert evidence_id in payload["evidence"], evidence_id


def test_evidence_rows_exist_and_paths_are_relative(payload) -> None:
    for evidence_id, block in payload["evidence"].items():
        assert block["rows"] is None or int(block["rows"]) >= 0
        path = Path(block["path"])
        assert not path.is_absolute(), evidence_id
        assert ".." not in path.parts, evidence_id


def test_farm04_blurple_area_is_invalid_and_not_drawn(payload) -> None:
    blurple = payload["series"]["farm-04-blurple"]["area_px"]
    assert blurple["series_state"] == "invalid"
    assert blurple["draw"] == "hatch"
    assert blurple["runs"] == []
    assert blurple["stats"]["median"] == 28
    white = payload["series"]["farm-04-white"]["area_px"]
    assert white["series_state"] == "ok"
    assert white["draw"] == "solid"
    assert white["stats"]["median"] == 480097.5


def test_no_area_drop_from_gated_rows(payload) -> None:
    assert not [f for f in payload["findings"] if f["rule_id"] == "area-drop"]


def test_validity_violation_aggregates_per_day(payload) -> None:
    violations = [
        finding for finding in payload["findings"]
        if finding["rule_id"] == "validity-violation"
    ]
    assert violations
    assert len(violations) < 20
    keys = {
        (finding["panel"], finding["window_start"], finding["detail"])
        for finding in violations
    }
    assert len(keys) == len(violations)


def test_two_condition_sides_never_average(payload) -> None:
    assert payload["conditions"]["switch_at"] == "2026-11-05T11:42:21Z"
    conditions = {
        payload["series"]["farm-04-blurple"]["area_px"]["condition_key"],
        payload["series"]["farm-04-white"]["area_px"]["condition_key"],
    }
    assert len(conditions) == 2
    assert all("light=" in condition for condition in conditions)


def test_page_contains_invalid_badge_and_light_sides(page) -> None:
    html, _result = page
    blurple = re.search(
        r'<article class="pv-card" id="pv-card-cd-area-line--farm-04-blurple".*?</article>',
        html,
        re.S,
    )
    assert blurple is not None
    assert 'data-state="invalid"' in blurple.group(0)
    assert "🔒" in blurple.group(0)
    white = re.search(
        r'<article class="pv-card" id="pv-card-cd-area-line--farm-04-white".*?</article>',
        html,
        re.S,
    )
    assert white is not None
    assert 'data-state="invalid"' not in white.group(0)
    compare = re.search(
        r'<article class="pv-card" id="pv-card-cd-light-compare--farm-04-blurple".*?</article>',
        html,
        re.S,
    )
    assert compare is not None
    assert 'data-state="invalid"' in compare.group(0)
    assert "blurple" in compare.group(0) and "white" in compare.group(0)


def test_page_has_data_quality_scale_subtab(page) -> None:
    html, _result = page
    assert 'data-tab="data-quality" data-sub="scale"' in html
    assert 'id="pv-card-dq-scale-stacked"' in html


def test_page_build_twice_identical_html(panels, tmp_path: Path) -> None:
    first = tmp_path / "a.html"
    second = tmp_path / "b.html"
    build_report(panels, first, now=NOW, title="Gate 2", include_frames=False)
    build_report(panels, second, now=NOW, title="Gate 2", include_frames=False)
    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(
        second.read_bytes()
    ).hexdigest()


def test_page_and_payload_budgets(page) -> None:
    html, result = page
    assert len(html.encode("utf-8")) <= 1_048_576
    assert result.json_bytes <= 320_000
    assert len(html) >= 1


def test_blank_never_zero() -> None:
    block = derive.series_block(
        [{"captured_at": "2026-11-03T06:00:00Z", "area_px": ""}],
        "area_px",
        unit="px",
        decimals=0,
    )
    assert block.measured == 0
    assert block.stats is None


def test_zero_is_real_when_measured() -> None:
    block = derive.series_block(
        [{"captured_at": "2026-11-03T06:00:00Z", "area_px": "0"}],
        "area_px",
        unit="px",
        decimals=0,
    )
    assert block.measured == 1
    assert block.stats["median"] == 0.0


def test_validity_beats_quality(tmp_path: Path) -> None:
    table = load_validity(ROOT / "data" / "derived" / "validity.csv")
    panel = Panel(
        id="p",
        label="P",
        crop="lettuce",
        method="exg",
        method_label="m",
        csv_path=tmp_path / "x.csv",
        pipeline_version="farm04-exg-0.1",
        light_regime="blurple",
        pose="side",
    )
    row = {
        "captured_at": "2026-11-03T06:00:00Z",
        "light_regime": "blurple",
        "camera_id": "farm-04",
        "scale_ok": "true",
        "area_px": "28",
        "quality_flag": "blur",
    }
    gated = gate.gate_rows([row], table, method_version="farm04-exg-0.1", panel=panel)
    assert gated[0].states["area_px"] == "invalid"
    assert gated[0].row["area_px"] == ""
    assert gated[0].row["quality_flag"] == "blur"


def test_quality_beats_missing(tmp_path: Path) -> None:
    table = load_validity(ROOT / "data" / "derived" / "validity.csv")
    panel = Panel(
        id="p",
        label="P",
        crop="lettuce",
        method="exg",
        method_label="m",
        csv_path=tmp_path / "x.csv",
        pipeline_version="farm04-exg-0.1",
        light_regime="white",
        pose="side",
    )
    row = {
        "captured_at": "2026-11-06T06:00:00Z",
        "light_regime": "white",
        "camera_id": "farm-04",
        "scale_ok": "true",
        "area_px": "480000",
        "quality_flag": "blur",
    }
    gated = gate.gate_rows([row], table, method_version="farm04-exg-0.1", panel=panel)
    assert gated[0].states["area_px"] == "valid"
    assert gated[0].row["area_px"] == "480000"
