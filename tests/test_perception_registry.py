"""Registry, crop-binding, and torch-free import tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from plantvision.ml.registry import (
    UnknownModelError,
    read_registry,
    write_registry_entry,
)
from plantvision.perception import get_perception, list_perception

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "basil:segformer-b0:v1"

ENTRY = {
    "arch": "segformer",
    "encoder": "mit_b0",
    "encoder_weights": None,
    "decoder_channels": 256,
    "classes": 1,
    "image_size": [288, 512],
    "threshold": 0.5,
    "checkpoint": "/nonexistent.pt",
    "crop_id": "basil",
}


def _registry(tmp_path: Path, models: dict | None = None) -> Path:
    """Write a temporary registry and return its path."""
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"models": models or {}}), encoding="utf-8")
    return path


def test_empty_registry_parses(tmp_path: Path) -> None:
    """``models: {}`` reads back as an empty mapping."""
    assert read_registry(_registry(tmp_path)) == {}


def test_real_registry_parses() -> None:
    """The committed registry parses whether empty or populated."""
    models = read_registry(REPO_ROOT / "configs" / "perception-registry.yaml")
    assert isinstance(models, dict)


def test_unknown_model_raises(tmp_path: Path) -> None:
    """An unregistered id raises UnknownModelError."""
    path = _registry(tmp_path, {MODEL_ID: ENTRY})
    with pytest.raises(UnknownModelError):
        get_perception("nope:segformer-b0:v1", crop_id="basil", registry_path=path)


def test_crop_mismatch_raises(tmp_path: Path) -> None:
    """A frame crop different from the entry crop fails before checkpoint load."""
    path = _registry(tmp_path, {MODEL_ID: ENTRY})
    with pytest.raises(ValueError) as excinfo:
        get_perception(MODEL_ID, crop_id="lettuce", registry_path=path)
    message = str(excinfo.value)
    assert "basil" in message and "lettuce" in message


def test_crop_required(tmp_path: Path) -> None:
    """An empty crop id is rejected."""
    path = _registry(tmp_path, {MODEL_ID: ENTRY})
    with pytest.raises(ValueError, match="crop_id is required"):
        get_perception(MODEL_ID, crop_id="", registry_path=path)


def test_list_perception_sorted(tmp_path: Path) -> None:
    """Registered ids are listed in sorted order."""
    path = _registry(
        tmp_path,
        {
            "zzz:segformer-b0:v1": {**ENTRY, "crop_id": "zzz"},
            "aaa:segformer-b0:v1": {**ENTRY, "crop_id": "aaa"},
        },
    )
    assert list_perception(path) == ["aaa:segformer-b0:v1", "zzz:segformer-b0:v1"]


def test_registry_write_refuses_overwrite_then_force(tmp_path: Path) -> None:
    """Writes are atomic and force is required to replace an id."""
    path = tmp_path / "registry.yaml"
    write_registry_entry(path, MODEL_ID, {**ENTRY, "sha256": "a" * 64})
    with pytest.raises(ValueError, match="already registered"):
        write_registry_entry(path, MODEL_ID, {**ENTRY, "sha256": "b" * 64})
    write_registry_entry(path, MODEL_ID, {**ENTRY, "sha256": "b" * 64}, force=True)
    assert read_registry(path)[MODEL_ID]["sha256"] == "b" * 64
    assert not (tmp_path / "registry.yaml.tmp").exists()


def test_src_has_no_crop_literal() -> None:
    """Crop ids never appear as literals in ``src/``."""
    offenders: list[str] = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for literal in ('"basil"', "'basil'", '"lettuce"', "'lettuce'"):
            if literal in text:
                offenders.append(f"{path}: {literal}")
    assert not offenders, offenders


def test_ml_and_perception_import_without_torch() -> None:
    """Importing the ML packages never pulls torch into ``sys.modules``."""
    code = (
        "import sys; import plantvision.ml.train, plantvision.ml.eval, "
        "plantvision.ml.dataset, plantvision.ml.transforms, plantvision.perception; "
        "assert 'torch' not in sys.modules, sorted(m for m in sys.modules if m == 'torch')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
