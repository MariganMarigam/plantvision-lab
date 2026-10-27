"""Read/resolve/write the local perception-model registry."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import yaml

REQUIRED_ENTRY_KEYS: tuple[str, ...] = (
    "arch",
    "encoder",
    "encoder_weights",
    "decoder_channels",
    "checkpoint",
    "image_size",
    "classes",
    "threshold",
)


class UnknownModelError(KeyError):
    """Raised when a requested model id is not registered."""


def repo_root() -> Path:
    """Return the repository root (three levels above this module)."""
    return Path(__file__).resolve().parents[3]


def read_registry(path: Path) -> dict[str, dict]:
    """Read ``models`` from a registry YAML file.

    Args:
        path: Registry path.

    Returns:
        Mapping ``model_id -> entry``.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the file has no ``models`` mapping.
    """
    if not path.is_file():
        raise FileNotFoundError(f"registry not found: {path}")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"registry {path} must be a mapping")
    models = document.get("models")
    if not isinstance(models, Mapping):
        raise ValueError(f"registry {path} needs a 'models' mapping")
    return {str(key): dict(value) for key, value in models.items()}


def resolve_entry(
    registry: Mapping[str, Mapping[str, object]],
    model_id: str,
    crop_id: str,
) -> dict[str, object]:
    """Resolve a model entry and check its crop binding.

    Args:
        registry: Mapping ``model_id -> entry``.
        model_id: Requested model id.
        crop_id: Crop of the frame being processed.

    Returns:
        A copy of the registry entry.

    Raises:
        UnknownModelError: If ``model_id`` is not registered.
        ValueError: Empty ``crop_id``, crop mismatch, or missing entry keys.
    """
    if model_id not in registry:
        raise UnknownModelError(model_id)
    if not str(crop_id).strip():
        raise ValueError("crop_id is required")
    entry = dict(registry[model_id])
    entry_crop = entry.get("crop_id")
    if entry_crop is None or entry_crop != crop_id:
        raise ValueError(
            f"model {model_id} is for crop {entry_crop!r}, frame crop is {crop_id!r}"
        )
    missing = [key for key in REQUIRED_ENTRY_KEYS if key not in entry]
    if missing:
        raise ValueError(f"registry entry {model_id} missing keys: {missing}")
    return entry


def write_registry_entry(
    path: Path,
    model_id: str,
    entry: Mapping[str, object],
    *,
    force: bool = False,
) -> Path:
    """Insert or replace one registry entry atomically.

    Args:
        path: Registry path; parents are created.
        model_id: Model id to write.
        entry: Entry payload.
        force: Replace an existing id when true.

    Returns:
        ``path``.

    Raises:
        ValueError: If ``model_id`` exists and ``force`` is false.
    """
    models: dict[str, dict] = {}
    if path.is_file():
        models = read_registry(path)
    if model_id in models and not force:
        raise ValueError(f"model id already registered: {model_id}")
    models[model_id] = dict(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".yaml.tmp")
    temporary.write_text(
        yaml.safe_dump({"models": models}, sort_keys=True), encoding="utf-8"
    )
    temporary.replace(path)
    return path
