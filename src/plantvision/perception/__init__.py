"""Torch-free perception facade over the local model registry."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from plantvision.ml.registry import read_registry, repo_root, resolve_entry

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np

DEFAULT_REGISTRY: str = "configs/perception-registry.yaml"


class BackendUnavailable(RuntimeError):
    """Raised when a registered backend cannot be constructed or verified."""


def _registry_path(explicit: Path | None) -> Path:
    """Resolve the registry path: argument, env var, then repo default."""
    if explicit is not None:
        return Path(explicit)
    from_env = os.environ.get("PLANTVISION_REGISTRY")
    if from_env:
        return Path(from_env)
    return repo_root() / DEFAULT_REGISTRY


def get_perception(
    model_id: str,
    *,
    crop_id: str,
    device: str = "auto",
    registry_path: Path | None = None,
) -> Callable[["np.ndarray"], "np.ndarray"]:
    """Build the perception callable registered for ``model_id``.

    Args:
        model_id: Registered model id, e.g. ``"basil:segformer-b0:v1"``.
        crop_id: Crop of the frame; must match the registry entry.
        device: ``auto``, ``cuda``, or ``cpu``.
        registry_path: Override of the registry file.

    Returns:
        A callable mapping a BGR image to a contract-valid ``(H, W)`` uint8
        mask.

    Raises:
        FileNotFoundError: Registry file missing.
        UnknownModelError: ``model_id`` not registered.
        ValueError: Empty or mismatched ``crop_id``.
        BackendUnavailable: Unsupported architecture.
    """
    models = read_registry(_registry_path(registry_path))
    entry = resolve_entry(models, model_id, crop_id)
    if entry["arch"] != "segformer":
        raise BackendUnavailable(f"unsupported arch: {entry['arch']!r}")
    from plantvision.perception.segformer import SegformerPerception

    return SegformerPerception(entry, device=device)


def list_perception(registry_path: Path | None = None) -> list[str]:
    """List registered model ids.

    Args:
        registry_path: Override of the registry file.

    Returns:
        Sorted model ids.
    """
    return sorted(read_registry(_registry_path(registry_path)))
