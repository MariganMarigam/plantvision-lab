"""Tests for the capture_once CLI logic (Stage 2 Task 2.6)."""

import json
import math
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import yaml

import plantvision.capture.capture_once as capture_once
from plantvision.capture.capture_once import in_light_window, run_once
from plantvision.capture.pull import CaptureError


def _jpeg_bytes() -> bytes:
    """A real small JPEG for the mocked pipeline."""
    ok, buf = cv2.imencode(".jpg", np.full((8, 12, 3), (80, 160, 160), np.uint8))
    assert ok
    return buf.tobytes()


def _make_config(tmp_path: Path, **overrides) -> Path:
    """Write a capture config with all paths redirected into tmp_path."""
    cfg = {
        "camera_id": "phone-01",
        "zone_id": "shelf-a/tray-1",
        "source_url": "http://example.invalid:8080/photo.jpg",
        "interval_minutes": 10,
        "timeout_seconds": 10,
        "retry_max": 5,
        "retry_backoff_seconds": [0, 0, 0, 0, 0],
        "resolution": [1280, 720],
        "originals_dir": str(tmp_path / "originals"),
        "spool_dir": str(tmp_path / "spool"),
        "log_path": str(tmp_path / "capture.log"),
        "light_window": {"start": "06:00", "end": "22:00", "tz": "local"},
        "dark_policy": "skip",
    }
    cfg.update(overrides)
    config_path = tmp_path / "capture.yaml"
    config_path.write_text(yaml.safe_dump(cfg))
    return config_path


def _log_lines(config_path: Path) -> list[dict]:
    log_path = Path(yaml.safe_load(config_path.read_text())["log_path"])
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text().splitlines()]


# Pin now_local to daytime so tests are independent of the host clock.
_DAYTIME_NOW = lambda tz: datetime(2026, 1, 1, 12, 0, 0)


def test_run_once_ok(tmp_path, monkeypatch) -> None:
    data = _jpeg_bytes()
    monkeypatch.setattr(capture_once, "fetch_photo", lambda url, timeout_s=10.0: data)
    monkeypatch.setattr(capture_once, "_local_now", _DAYTIME_NOW)
    config_path = _make_config(tmp_path)
    result = run_once(config_path)
    assert result["status"] == "ok"
    stored = list((tmp_path / "originals").rglob("*.jpg"))
    assert len(stored) == 1
    assert result["path"] == str(stored[0])
    assert result["sha256"] == capture_once.build_metadata(
        data, "2026-01-01T00:00:00.000000Z", phone_id := "phone-01", "z"
    )["sha256"]
    assert _log_lines(config_path)[-1]["status"] == "ok"


def test_run_once_duplicate(tmp_path, monkeypatch) -> None:
    data = _jpeg_bytes()
    monkeypatch.setattr(capture_once, "fetch_photo", lambda url, timeout_s=10.0: data)
    monkeypatch.setattr(capture_once, "_utc_now", lambda: "2026-01-01T10:00:00.000000Z")
    monkeypatch.setattr(capture_once, "_local_now", _DAYTIME_NOW)
    config_path = _make_config(tmp_path)
    first = run_once(config_path)
    result = run_once(config_path)
    assert first["status"] == "ok"
    assert result["status"] == "duplicate"
    stored = list((tmp_path / "originals").rglob("*.jpg"))
    assert len(stored) == 1


def test_run_once_gap(tmp_path, monkeypatch) -> None:
    def _boom(url: str, timeout_s: float = 10.0) -> bytes:
        raise CaptureError("connection refused")

    monkeypatch.setattr(capture_once, "fetch_photo", _boom)
    monkeypatch.setattr(capture_once, "_local_now", _DAYTIME_NOW)
    config_path = _make_config(tmp_path, retry_max=1, retry_backoff_seconds=[0, 0])
    result = run_once(config_path)
    assert result["status"] == "error"
    records = _log_lines(config_path)
    assert records[-1]["status"] == "gap"
    assert not list((tmp_path / "originals").rglob("*.jpg")) if (tmp_path / "originals").exists() else True


def test_run_once_skips_dark(tmp_path, monkeypatch) -> None:
    called = False

    def _must_not_fetch(url: str, timeout_s: float = 10.0) -> bytes:
        raise AssertionError("fetch_photo must not be called in the dark window")

    monkeypatch.setattr(capture_once, "_local_now", lambda tz: datetime(2026, 1, 1, 23, 0, 0))
    monkeypatch.setattr(capture_once, "fetch_photo", _must_not_fetch)
    config_path = _make_config(tmp_path)
    result = run_once(config_path)
    assert result["status"] == "skipped_dark"
    assert not (tmp_path / "originals").exists()
    assert _log_lines(config_path)[-1]["status"] == "skipped_dark"


def test_in_light_window_boundaries() -> None:
    assert in_light_window(datetime(2026, 1, 1, 6, 0), "06:00", "22:00") is True
    assert in_light_window(datetime(2026, 1, 1, 12, 0), "06:00", "22:00") is True
    assert in_light_window(datetime(2026, 1, 1, 22, 0), "06:00", "22:00") is False


def test_in_light_window_wrap() -> None:
    assert in_light_window(datetime(2026, 1, 1, 23, 0), "22:00", "06:00") is True
    assert in_light_window(datetime(2026, 1, 1, 5, 59), "22:00", "06:00") is True
    assert in_light_window(datetime(2026, 1, 1, 6, 0), "22:00", "06:00") is False
    assert in_light_window(datetime(2026, 1, 1, 12, 0), "22:00", "06:00") is False
