"""Checkpoint-backed SegFormer perception behind the frozen contract."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import cv2
import numpy as np

from plantvision.ml.model import (
    ModelConfig,
    build_model,
    load_checkpoint,
    sha256_file,
)
from plantvision.ml.registry import repo_root
from plantvision.ml.transforms import MEAN, STD, build_eval_transform
from plantvision.perception import BackendUnavailable
from plantvision.vision.interfaces import check_mask

MIN_SIDE: int = 32


class SegformerPerception:
    """Load one registered checkpoint and return native-resolution masks."""

    def __init__(
        self, entry: Mapping[str, object], *, device: str = "auto"
    ) -> None:
        """Load the checkpoint described by a registry entry.

        Args:
            entry: Registry entry with arch/checkpoint/image_size/threshold.
            device: ``auto``, ``cuda``, or ``cpu``.

        Raises:
            FileNotFoundError: Checkpoint file missing.
            BackendUnavailable: Checkpoint hash mismatch.
            ImportError: Torch/encoder stack not installed.
        """
        import torch

        self.device = self._resolve_device(device)
        self.checkpoint = self._checkpoint_path(str(entry["checkpoint"]))
        expected_sha = str(entry.get("sha256") or "")
        if expected_sha:
            actual_sha = sha256_file(self.checkpoint)
            if actual_sha != expected_sha:
                raise BackendUnavailable(
                    f"checkpoint sha256 mismatch: registry {expected_sha}, "
                    f"file {actual_sha} ({self.checkpoint})"
                )
        config = ModelConfig(
            arch=str(entry["arch"]),
            encoder=str(entry["encoder"]),
            encoder_weights=entry.get("encoder_weights"),  # type: ignore[arg-type]
            classes=int(entry["classes"]),
            decoder_channels=int(entry["decoder_channels"]),
        )
        model = build_model(config)
        load_checkpoint(self.checkpoint, model)
        self.model = model.to(self.device).eval()
        self.image_size = tuple(int(value) for value in entry["image_size"])
        self.threshold = float(entry["threshold"])
        self.mean = MEAN
        self.std = STD

    def _resolve_device(self, device: str) -> str:
        """Resolve ``auto`` to CUDA when available."""
        import torch

        if device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return device

    def _checkpoint_path(self, checkpoint: str) -> Path:
        """Resolve a checkpoint path against the repo root."""
        path = Path(checkpoint)
        if not path.is_absolute():
            path = repo_root() / path
        if not path.is_file():
            raise FileNotFoundError(f"checkpoint not found: {path}")
        return path

    def __call__(self, image: np.ndarray) -> np.ndarray:
        """Segment one BGR image at native resolution.

        Args:
            image: BGR uint8 image with shape ``(H, W, 3)``.

        Returns:
            ``(H, W)`` uint8 mask with values in ``{0, 255}``.

        Raises:
            ValueError: Non-uint8, grayscale, or smaller than 32x32 input.
        """
        import torch
        import torch.nn.functional as functional

        self._validate_image(image)
        height, width = image.shape[:2]
        use_cuda = self.device.startswith("cuda")
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        tensor = build_eval_transform(self.image_size)(image=rgb)["image"]
        tensor = tensor.unsqueeze(0).to(self.device)
        with torch.no_grad(), torch.autocast(
            device_type="cuda", dtype=torch.bfloat16, enabled=use_cuda
        ):
            logits = self.model(tensor)
        prob = torch.sigmoid(logits.float())
        upsampled = functional.interpolate(
            prob, size=(height, width), mode="bilinear", align_corners=False
        )
        binary = (upsampled >= self.threshold).to(torch.uint8) * 255
        mask = binary[0, 0].cpu().numpy().astype(np.uint8)
        check_mask(mask, image)
        return mask

    @staticmethod
    def _validate_image(image: np.ndarray) -> None:
        """Validate the frozen BGR contract before inference."""
        if not isinstance(image, np.ndarray):
            raise ValueError(f"image must be a numpy array, got {type(image)!r}")
        if image.dtype != np.uint8:
            raise ValueError(f"image must be uint8, got {image.dtype}")
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"image must be (H, W, 3), got {image.shape}")
        height, width = image.shape[:2]
        if height < MIN_SIDE or width < MIN_SIDE:
            raise ValueError(
                f"image must be at least {MIN_SIDE}x{MIN_SIDE}, got {image.shape}"
            )
