"""Tests for configs/capture.yaml (Stage 2 Task 2.1)."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_capture_config_keys() -> None:
    """All 13 Stage-2 capture keys exist with the specified cadence/light values."""
    cfg = yaml.safe_load((REPO_ROOT / "configs" / "capture.yaml").read_text())
    expected = {
        "camera_id",
        "zone_id",
        "source_url",
        "interval_minutes",
        "timeout_seconds",
        "retry_max",
        "retry_backoff_seconds",
        "resolution",
        "originals_dir",
        "spool_dir",
        "log_path",
        "light_window",
        "dark_policy",
    }
    assert expected <= set(cfg)
    assert cfg["interval_minutes"] == 1
    assert cfg["light_window"]["start"] == "06:00"
    assert cfg["dark_policy"] == "skip"
