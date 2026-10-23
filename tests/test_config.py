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
    assert cfg["interval_minutes"] == 10
    assert cfg["light_window"]["start"] == "06:00"
    assert cfg["dark_policy"] == "skip"


def test_capture_white_config() -> None:
    """White-light profile mirrors capture-farm except identity/light window (P1.3)."""
    cfg = yaml.safe_load((REPO_ROOT / "configs" / "capture-white.yaml").read_text())
    farm = yaml.safe_load((REPO_ROOT / "configs" / "capture-farm.yaml").read_text())
    assert cfg["camera_id"] == "farm-white-01"
    assert cfg["zone_id"] == "farm/zone-a-white"
    assert cfg["crop_id"] == "basil"
    assert cfg["interval_minutes"] == 5
    assert cfg["resolution"] == [720, 1280]
    assert cfg["light_window"] == {"start": "00:00", "end": "23:59", "tz": "local"}
    for key in ("originals_dir", "spool_dir", "log_path", "dark_policy", "import"):
        assert cfg[key] == farm[key]


def test_pipeline_config_keys() -> None:
    """All Stage-05 pipeline keys exist with the plan-specified defaults."""
    cfg = yaml.safe_load((REPO_ROOT / "configs" / "pipeline.yaml").read_text())
    assert {"roi", "scale_reference", "segmentation", "quality", "metrics", "pipeline_version"} <= set(cfg)
    assert cfg["segmentation"]["method"] == "hsv"
    assert cfg["quality"]["blur_lapvar_min"] == 10.0
    assert cfg["scale_reference"]["dict"] == "DICT_5X5_50"
    assert cfg["scale_reference"]["marker_size_mm"] == 45
    assert "projected_area_cm2" in cfg["metrics"]
