"""SAM2 box-prompt segmenter with LAZY torch/sam2 imports.

Importing this module and everything under ``plantvision.labeling`` MUST
work with torch absent; ``torch`` and ``sam2`` are imported only inside
``Sam2Segmenter.__init__`` and inside ``segment`` (plan Step 7, guarded
by ``tests/test_labeling_isolation.py``). SAM2 is a label producer only:
its masks never enter the measurement path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from plantvision.vision.segmentation import largest_component


class Sam2Error(RuntimeError):
    """Raised when torch/sam2 import fails or the device cannot be used."""


@dataclass(frozen=True)
class MaskProposal:
    """One SAM2 box-prompt result, contract-clean for the mask store."""

    mask: np.ndarray  # (H, W) uint8 in {0, 255}
    score: float  # iou prediction of the chosen mask
    box: tuple[int, int, int, int]  # inclusive prompt box used


class Sam2Segmenter:
    """Single-image SAM2 wrapper: one box prompt -> largest component mask.

    Args are validated before any model interaction so the CLI can batch
    frames and skip per-frame errors without model state corruption.

    Raises in ``__init__`` (so the CLI maps them to exit code 2):
        FileNotFoundError: checkpoint path does not exist; see plan
            Section 1.3.
        Sam2Error: torch/sam2 not importable, or ``cuda`` requested while
            ``torch.cuda.is_available()`` is False.
    """

    def __init__(
        self,
        checkpoint: Path,
        config: str = "configs/sam2.1/sam2.1_hiera_s.yaml",
        device: str = "auto",
    ) -> None:
        checkpoint = Path(checkpoint)
        if not checkpoint.exists():
            raise FileNotFoundError(
                f"checkpoint not found: {checkpoint}; see plan Section 1.3"
            )
        try:
            import torch
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor
        except ImportError as exc:
            raise Sam2Error(
                f"SAM2 not installed; see plan Section 1.3 ({exc})"
            ) from exc
        if device == "auto":
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        elif device == "cuda" and not torch.cuda.is_available():
            raise Sam2Error("cuda requested but torch.cuda.is_available() is False")
        else:
            self._device = device
        model = build_sam2(config, str(checkpoint), device=self._device)
        self._predictor = SAM2ImagePredictor(model)

    @property
    def device(self) -> str:
        """Resolved torch device string (``"cuda"`` or ``"cpu"``)."""
        return self._device

    def segment(
        self, image_bgr: np.ndarray, box: tuple[int, int, int, int]
    ) -> MaskProposal:
        """Run one box-prompted prediction and clean the mask.

        Args:
            image_bgr: BGR uint8 ``(H, W, 3)`` frame.
            box: Inclusive ``(x1, y1, x2, y2)`` within the frame.

        Returns:
            MaskProposal with an all-zero mask allowed (score kept) — the
            human reviewer rejects degenerate output, no silent retry.

        Raises:
            ValueError: If the image is not 3-channel or the box is not
                strictly inside the frame.
            torch.cuda.OutOfMemoryError: Propagated (CLI records the
                frame as an error; operator reruns with ``--device cpu``).
        """
        import torch

        if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
            raise ValueError(
                f"expected (H, W, 3) BGR image, got shape={image_bgr.shape}"
            )
        height, width = image_bgr.shape[:2]
        x1, y1, x2, y2 = box
        if not (0 <= x1 < x2 <= width - 1 and 0 <= y1 < y2 <= height - 1):
            raise ValueError(
                f"box {box} not strictly inside frame (W={width}, H={height})"
            )
        rgb = np.ascontiguousarray(image_bgr[:, :, ::-1])
        self._predictor.set_image(rgb)
        with torch.inference_mode():
            if self._device == "cuda":
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    masks, scores, _ = self._predictor.predict(
                        box=np.array(box, dtype=np.float32)[None, :],
                        multimask_output=True,
                    )
            else:
                masks, scores, _ = self._predictor.predict(
                    box=np.array(box, dtype=np.float32)[None, :],
                    multimask_output=True,
                )
        arr = np.asarray(masks)
        if arr.ndim == 4:
            arr = arr[0]
        iou = np.asarray(scores).reshape(-1)
        best = int(np.argmax(iou))
        binary = (arr[best] > 0).astype(np.uint8) * 255
        clean = largest_component(binary)
        return MaskProposal(mask=clean, score=float(iou[best]), box=box)
