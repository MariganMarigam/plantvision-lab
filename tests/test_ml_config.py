"""Training config, CLI help, and run-artifact ignore tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from plantvision.ml.train import load_train_config

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "configs" / "train.yaml"
EXPORT = REPO_ROOT / "data" / "labels" / "farm02-v1" / "export" / "yolo-seg"
GATE_KEYS = (
    "min_val_dice",
    "min_test_dice",
    "min_test_iou",
    "min_test_recall",
    "max_area_abs_pct_error_median",
    "max_area_abs_pct_error_p90",
    "max_vram_gb",
    "max_train_minutes",
)


def test_train_config_parses() -> None:
    """The real training config parses into typed values."""
    cfg = load_train_config(CONFIG)
    assert cfg.image_size == (512, 288)
    assert cfg.image_size[0] % 32 == 0 and cfg.image_size[1] % 32 == 0
    assert cfg.dataset["expected_image_size"] == (1280, 720)
    assert cfg.batch_size == 8
    assert cfg.epochs == 80
    assert cfg.crop_id == "basil"
    assert cfg.model_id == "basil:segformer-b0:v1"
    assert cfg.threshold == pytest.approx(0.5)
    for key in GATE_KEYS:
        assert key in cfg.gate


@pytest.mark.skipif(
    not EXPORT.is_dir(), reason="farm-02 yolo-seg export is absent (gitignored)"
)
def test_config_paths_exist() -> None:
    """Every config path resolves to a real file or directory."""
    cfg = load_train_config(CONFIG)
    assert Path(cfg.dataset["root"]).is_dir()
    assert Path(cfg.dataset["manifest"]).is_file()
    assert Path(cfg.dataset["sam2_masks"]).is_dir()
    assert Path(cfg.checkpoint["dir"]).is_dir()
    assert Path(cfg.registry["path"]).is_file()


def _mutated_config(tmp_path: Path, mutate) -> Path:
    """Copy the real config to ``tmp_path`` and apply ``mutate``."""
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    mutate(data)
    target = tmp_path / "train.yaml"
    target.write_text(yaml.safe_dump(data), encoding="utf-8")
    return target


def test_config_rejects_bad_image_size(tmp_path: Path) -> None:
    """A non-multiple-of-32 image size is rejected."""

    def mutate(data: dict) -> None:
        data["image_size"] = [300, 512]

    with pytest.raises(ValueError, match="multiples of 32"):
        load_train_config(_mutated_config(tmp_path, mutate))


def test_config_rejects_missing_keys(tmp_path: Path) -> None:
    """A removed required key is reported by name."""

    def mutate(data: dict) -> None:
        del data["lr"]

    with pytest.raises(ValueError, match="missing keys"):
        load_train_config(_mutated_config(tmp_path, mutate))


def test_gitignore_covers_experiments() -> None:
    """Run artifacts are ignored while the directory placeholder is not."""
    lines = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "experiments/*" in lines
    assert "!experiments/.gitkeep" in lines


def _run_help(script: str) -> subprocess.CompletedProcess[str]:
    """Run one script's ``--help`` from the repo root."""
    return subprocess.run(
        [sys.executable, f"scripts/{script}", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_train_cli_help() -> None:
    """The training CLI documents ``--run-id``."""
    result = _run_help("train_segformer.py")
    assert result.returncode == 0
    assert "--run-id" in result.stdout


def test_eval_cli_help() -> None:
    """The evaluation CLI documents ``--register``."""
    result = _run_help("eval_segformer.py")
    assert result.returncode == 0
    assert "--register" in result.stdout
