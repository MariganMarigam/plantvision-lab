"""Tests for the idempotent original store (Stage 2 Task 2.4)."""

import json

from plantvision.capture.store import store_original

BYTES = b"\xff\xd8test-frame-bytes\xff\xd9"
META = {
    "sha256": "a" * 64,
    "captured_at": "2026-10-13T12:00:00.000000Z",
    "camera_id": "phone-01",
    "zone_id": "shelf-a/tray-1",
}


def test_store_then_duplicate(tmp_path) -> None:
    path1, stored1 = store_original(BYTES, META, tmp_path)
    path2, stored2 = store_original(BYTES, META, tmp_path)
    assert stored1 is True
    assert stored2 is False
    assert path1 == path2
    # Layout: originals_dir/<camera_id>/<zone_slug>/<day>/
    parts = path1.relative_to(tmp_path).parts
    assert parts[:3] == ("phone-01", "shelf-a_tray-1", "2026-10-13")
    jpgs = [f for f in tmp_path.rglob("*") if f.is_file() and f.suffix == ".jpg"]
    jsons = [f for f in tmp_path.rglob("*") if f.is_file() and f.suffix == ".json"]
    assert len(jpgs) == 1
    assert len(jsons) == 1


def test_store_writes_sidecar(tmp_path) -> None:
    path, _ = store_original(BYTES, META, tmp_path)
    sidecar = json.loads(path.with_suffix(".json").read_text())
    assert sidecar["sha256"] == META["sha256"]
    assert "received_at" in sidecar
