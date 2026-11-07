"""Schema, golden-mirror and determinism tests for the v3 service (B0)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from plantvision.analytics.dashboard.build import Panel
from plantvision.analytics.dashboard.model import build_payload as legacy_build_payload
from plantvision.analytics.service import (
    ContractError,
    ServiceOptions,
    SourcePaths,
    build_payload,
)
from plantvision.analytics.service.validate import META_KEYS, SCHEMA, validate_payload

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "gate2"
GOLDEN = ROOT / "tests" / "fixtures" / "golden" / "pv-dashboard-v2.json"
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
EXPECTED_SECTIONS = {
    "meta", "conditions", "panels", "series", "measurements", "validity",
    "evidence", "tables", "cards", "links", "findings", "snapshots", "render",
}


def _panels() -> list[Panel]:
    """Two tiny fixture panels over the gate2 CSVs."""
    return [
        Panel(
            id="fixture-a",
            label="Fixture A",
            crop="fixture",
            method="exg",
            method_label="fixture method",
            csv_path=Path("tests/fixtures/gate2/store-a.csv"),
            pipeline_version="fixture-a-0.1",
        ),
        Panel(
            id="fixture-b",
            label="Fixture B",
            crop="fixture",
            method="exg",
            method_label="fixture method",
            csv_path=Path("tests/fixtures/gate2/store-b.csv"),
            pipeline_version="fixture-b-0.1",
        ),
    ]


def _payload(options: ServiceOptions | None = None) -> dict[str, object]:
    return build_payload(
        _panels(),
        NOW,
        options or ServiceOptions(),
        sources=SourcePaths(validity=ROOT / "data" / "derived" / "validity.csv"),
    )


def test_payload_schema_version() -> None:
    assert _payload()["meta"]["schema"] == SCHEMA == "pv-dashboard/3"


def test_meta_keys_exact() -> None:
    payload = _payload()
    assert set(payload["meta"]) == set(META_KEYS)
    assert set(payload) >= EXPECTED_SECTIONS
    assert payload["meta"]["options"] == {"window": "all", "agg": "raw", "mode": "abs"}


def test_v2_mirror_is_byte_identical() -> None:
    payload = _payload()
    expected = legacy_build_payload(
        _panels(), now=NOW, title="Plant CV Lab · growth dashboard"
    )
    canonical = json.dumps(
        payload["legacy"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    reference = json.dumps(
        expected, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert canonical == reference
    if GOLDEN.exists():
        assert canonical == GOLDEN.read_text(encoding="utf-8")


def test_nullability_matrix() -> None:
    payload = _payload()
    payload["meta"]["generated_at"] = None
    validate_payload(payload)
    payload["meta"]["title"] = None
    with pytest.raises(ContractError):
        validate_payload(payload)


def test_schema_validator_rejects_type_change() -> None:
    payload = _payload()
    payload["meta"]["schema"] = 3
    with pytest.raises(ContractError):
        validate_payload(payload)


def test_unknown_key_policy() -> None:
    payload = _payload()
    payload["meta"]["additive"] = {"ok": True}
    validate_payload(payload)
    del payload["meta"]["schema"]
    with pytest.raises(ContractError):
        validate_payload(payload)


def test_build_twice_identical_json() -> None:
    first = _payload()
    second = _payload()
    assert json.dumps(first, sort_keys=True, ensure_ascii=False) == json.dumps(
        second, sort_keys=True, ensure_ascii=False
    )


def test_no_crop_literals_in_service() -> None:
    forbidden = ("lettuce", "basil", "phone-01", "farm-04", "farm-03", "farm-02")
    for path in sorted((ROOT / "src" / "plantvision" / "analytics" / "service").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for word in forbidden:
            assert word not in text, f"{path.name} contains crop literal {word}"


def test_validity_section_shape() -> None:
    payload = _payload()
    validity = payload["validity"]
    assert set(validity) == {"rows", "by_key", "matrix", "counts"}
    assert validity["counts"] == {"valid": 2, "invalid": 2, "unproven": 2}
    for evidence_id, block in payload["evidence"].items():
        assert not Path(block["path"]).is_absolute(), evidence_id
        assert ".." not in Path(block["path"]).parts, evidence_id
