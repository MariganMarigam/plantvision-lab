"""SegFormer factory and checkpoint I/O.

Every torch import is function-local so that importing this module never loads
torch.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

CHUNK_SIZE: int = 1024 * 1024


@dataclass(frozen=True)
class ModelConfig:
    """Model architecture parameters persisted inside every checkpoint."""

    arch: str = "segformer"
    encoder: str = "mit_b0"
    encoder_weights: str | None = "imagenet"
    classes: int = 1
    decoder_channels: int = 256


def build_model(cfg: ModelConfig) -> "torch.nn.Module":
    """Build a one-class SegFormer segmentation model.

    Args:
        cfg: Architecture configuration.

    Returns:
        An untrained ``smp.Segformer`` with ``classes`` output channels.

    Raises:
        ValueError: If ``arch`` is not ``segformer`` or ``classes`` is not 1.
        ImportError: If ``segmentation-models-pytorch`` is not installed.
    """
    if cfg.arch != "segformer":
        raise ValueError(f"unsupported arch: {cfg.arch!r}")
    if cfg.classes != 1:
        raise ValueError(f"only classes=1 is supported, got {cfg.classes}")
    try:
        import segmentation_models_pytorch as smp
    except ImportError as exc:  # pragma: no cover - exercised only without extras
        raise ImportError("install requirements-ml.txt") from exc
    return smp.Segformer(
        encoder_name=cfg.encoder,
        encoder_weights=cfg.encoder_weights,
        decoder_segmentation_channels=cfg.decoder_channels,
        in_channels=3,
        classes=cfg.classes,
        activation=None,
    )


def count_parameters(model: "torch.nn.Module") -> int:
    """Count trainable parameters.

    Args:
        model: A torch module.

    Returns:
        Sum of ``numel()`` over parameters with ``requires_grad``.
    """
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def sha256_file(path: Path) -> str:
    """Hash a file with SHA-256.

    Args:
        path: File to hash.

    Returns:
        Lowercase hex digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_checkpoint(
    path: Path,
    model: "torch.nn.Module",
    optimizer: "torch.optim.Optimizer",
    scheduler: object | None,
    *,
    epoch: int,
    best_val_dice: float,
    meta: Mapping[str, Any],
) -> Path:
    """Write a training checkpoint.

    Args:
        path: Destination ``.pt`` path; parents are created.
        model: Model whose state dict is stored.
        optimizer: Optimizer whose state dict is stored.
        scheduler: Optional LR scheduler; ``None`` stores ``None``.
        epoch: Completed epoch index.
        best_val_dice: Best validation Dice seen so far.
        meta: JSON-safe metadata (model config, run provenance).

    Returns:
        ``path``.
    """
    import torch

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "scheduler": scheduler.state_dict() if scheduler is not None else None,
        "epoch": epoch,
        "best_val_dice": best_val_dice,
        "meta": dict(meta),
    }
    torch.save(payload, path)
    return path


def load_checkpoint(
    path: Path,
    model: "torch.nn.Module",
    optimizer: "torch.optim.Optimizer | None" = None,
    scheduler: object | None = None,
) -> dict[str, Any]:
    """Load a checkpoint into an already-built model.

    Args:
        path: Checkpoint path.
        model: Model with matching architecture.
        optimizer: Optional optimizer to restore.
        scheduler: Optional scheduler to restore.

    Returns:
        ``{"epoch", "best_val_dice", "meta"}``.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    import torch

    if not path.is_file():
        raise FileNotFoundError(f"checkpoint not found: {path}")
    payload = torch.load(path, map_location="cpu", weights_only=False)
    model.load_state_dict(payload["model"])
    if optimizer is not None and payload.get("optimizer") is not None:
        optimizer.load_state_dict(payload["optimizer"])
    if scheduler is not None and payload.get("scheduler") is not None:
        scheduler.load_state_dict(payload["scheduler"])
    return {
        "epoch": payload["epoch"],
        "best_val_dice": payload["best_val_dice"],
        "meta": payload["meta"],
    }
