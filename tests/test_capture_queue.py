"""Tests for the reconnect spool queue (Stage 2 Task 2.5)."""

from plantvision.capture.queue import CaptureQueue

BYTES = b"\xff\xd8spool-frame\xff\xd9"
META = {
    "sha256": "b" * 64,
    "captured_at": "2026-10-13T12:00:00.000000Z",
    "camera_id": "phone-01",
    "zone_id": "shelf-a/tray-1",
}


def test_add_items_remove(tmp_path) -> None:
    q = CaptureQueue(tmp_path)
    q.add(BYTES, META)
    assert len(q) == 1
    items = q.items()
    assert len(items) == 1
    jpg_path, meta = items[0]
    assert jpg_path.name == f"{META['sha256']}.jpg"
    assert jpg_path.read_bytes() == BYTES
    assert meta["sha256"] == META["sha256"]
    q.remove(META["sha256"])
    assert len(q) == 0
    assert not list(tmp_path.iterdir())
    q.remove(META["sha256"])  # already-removed sha -> no-op


def test_items_skips_bad_json(tmp_path) -> None:
    q = CaptureQueue(tmp_path)
    (tmp_path / "bad.json").write_text("{not json")
    (tmp_path / "bad.jpg").write_bytes(BYTES)
    assert q.items() == []
