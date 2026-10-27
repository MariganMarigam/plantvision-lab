"""Native-resolution metrics, projected-area error, and the promotion gate."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import cv2
import numpy as np

from plantvision.ml.dataset import Sample, parse_yolo_seg_label
from plantvision.ml.transforms import build_eval_transform
from plantvision.vision.scale import px_per_mm

PER_FRAME_COLUMNS: tuple[str, ...] = (
    "sha256",
    "dice",
    "iou",
    "precision",
    "recall",
    "pred_px",
    "gt_px",
    "area_error_pct",
    "area_cm2_pred",
    "area_cm2_gt",
    "label_ceiling_dice",
    "student_vs_sam2_dice",
    "marker",
)


def dice_score(pred: np.ndarray, gt: np.ndarray) -> float:
    """Dice overlap of two boolean masks.

    Args:
        pred: Predicted mask.
        gt: Ground-truth mask.

    Returns:
        Dice in ``[0, 1]``; two empty masks score ``1.0``.
    """
    predicted = np.asarray(pred).astype(bool)
    truth = np.asarray(gt).astype(bool)
    inter = float((predicted & truth).sum())
    return (2.0 * inter + 1e-9) / (
        float(predicted.sum()) + float(truth.sum()) + 1e-9
    )


def iou_score(pred: np.ndarray, gt: np.ndarray) -> float:
    """Intersection-over-union of two boolean masks.

    Args:
        pred: Predicted mask.
        gt: Ground-truth mask.

    Returns:
        IoU in ``[0, 1]``; two empty masks score ``1.0``.
    """
    predicted = np.asarray(pred).astype(bool)
    truth = np.asarray(gt).astype(bool)
    inter = float((predicted & truth).sum())
    union = float((predicted | truth).sum())
    return (inter + 1e-9) / (union + 1e-9)


def precision_recall(pred: np.ndarray, gt: np.ndarray) -> tuple[float, float]:
    """Pixel precision and recall.

    Args:
        pred: Predicted mask.
        gt: Ground-truth mask.

    Returns:
        ``(precision, recall)``; an empty ground truth scores ``1.0`` on both,
        and an empty prediction against a non-empty truth scores ``0.0`` on
        recall.
    """
    predicted = np.asarray(pred).astype(bool)
    truth = np.asarray(gt).astype(bool)
    tp = float((predicted & truth).sum())
    fp = float((predicted & ~truth).sum())
    fn = float((~predicted & truth).sum())
    if tp + fp == 0.0:
        precision = 1.0 if truth.sum() == 0 else 0.0
    else:
        precision = tp / (tp + fp)
    recall = 1.0 if tp + fn == 0.0 else tp / (tp + fn)
    return precision, recall


def area_error_pct(pred_px: int, gt_px: int) -> float:
    """Signed projected-area error in percent of the ground-truth area.

    Args:
        pred_px: Predicted pixel area.
        gt_px: Ground-truth pixel area.

    Returns:
        ``100 * (pred_px - gt_px) / gt_px``.

    Raises:
        ValueError: If ``gt_px`` is zero.
    """
    if gt_px == 0:
        raise ValueError("cannot compute area error for an empty ground truth")
    return 100.0 * float(pred_px - gt_px) / float(gt_px)


def summarize(values: Sequence[float]) -> dict[str, float]:
    """Summarize a metric list.

    Args:
        values: Metric values.

    Returns:
        ``mean``, ``median``, ``p90``, ``max``, and ``n``; all zeros when the
        list is empty (``n=0``).
    """
    if not values:
        return {"mean": 0.0, "median": 0.0, "p90": 0.0, "max": 0.0, "n": 0.0}
    array = np.asarray(list(values), dtype=np.float64)
    return {
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "p90": float(np.percentile(array, 90, method="linear")),
        "max": float(array.max()),
        "n": float(array.size),
    }


def predict_mask(
    model,
    image_bgr: np.ndarray,
    *,
    image_size: tuple[int, int],
    threshold: float,
    device: str,
    amp: bool,
) -> np.ndarray:
    """Predict a contract-valid native-resolution mask.

    Args:
        model: Segmentation model.
        image_bgr: Native BGR uint8 image.
        image_size: Model input ``(H, W)``.
        threshold: Probability threshold.
        device: Torch device string.
        amp: Enable bf16 autocast on CUDA.

    Returns:
        ``(H, W)`` uint8 mask with values in ``{0, 255}``.
    """
    import torch
    import torch.nn.functional as functional

    use_cuda = str(device).startswith("cuda")
    height, width = image_bgr.shape[:2]
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    tensor = build_eval_transform(image_size)(image=rgb)["image"]
    tensor = tensor.unsqueeze(0).to(device)
    model.eval()
    with torch.no_grad(), torch.autocast(
        device_type="cuda", dtype=torch.bfloat16, enabled=amp and use_cuda
    ):
        logits = model(tensor)
    prob = torch.sigmoid(logits.float())
    upsampled = functional.interpolate(
        prob, size=(height, width), mode="bilinear", align_corners=False
    )
    binary = (upsampled >= threshold).to(torch.uint8) * 255
    return binary[0, 0].cpu().numpy().astype(np.uint8)


def _sam2_mask(path: Path) -> np.ndarray | None:
    """Read a SAM2 PNG as a boolean mask, or ``None`` when absent."""
    if not path.is_file():
        return None
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"cannot read SAM2 mask: {path}")
    return mask > 127


def _frame_row(
    sample: Sample,
    pred: np.ndarray,
    native: np.ndarray,
    *,
    ppm: float | None,
    sam2_masks: Path | None,
) -> dict[str, object]:
    """Build one per-frame metric row."""
    predicted = pred > 127
    truth = native > 127
    pred_px = int(predicted.sum())
    gt_px = int(truth.sum())
    precision, recall = precision_recall(predicted, truth)
    row: dict[str, object] = {
        "sha256": sample.sha256,
        "dice": dice_score(predicted, truth),
        "iou": iou_score(predicted, truth),
        "precision": precision,
        "recall": recall,
        "pred_px": pred_px,
        "gt_px": gt_px,
        "area_error_pct": area_error_pct(pred_px, gt_px),
        "area_cm2_pred": None,
        "area_cm2_gt": None,
        "label_ceiling_dice": None,
        "student_vs_sam2_dice": None,
        "marker": ppm is not None,
    }
    if ppm is not None:
        row["area_cm2_pred"] = pred_px / (ppm**2) / 100.0
        row["area_cm2_gt"] = gt_px / (ppm**2) / 100.0
    if sam2_masks is not None:
        sam2 = _sam2_mask(sam2_masks / f"{sample.sha256}.png")
        if sam2 is not None:
            row["label_ceiling_dice"] = dice_score(truth, sam2)
            row["student_vs_sam2_dice"] = dice_score(predicted, sam2)
    return row


def _aggregate(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Aggregate per-frame rows into one split summary."""

    def values(key: str) -> list[float]:
        return [float(row[key]) for row in rows if row.get(key) is not None]

    dice = summarize(values("dice"))
    iou = summarize(values("iou"))
    precision = summarize(values("precision"))
    recall = summarize(values("recall"))
    abs_error = summarize([abs(value) for value in values("area_error_pct")])
    signed = summarize(values("area_error_pct"))
    cm2_pairs = [
        abs(float(row["area_cm2_pred"]) - float(row["area_cm2_gt"]))
        for row in rows
        if row.get("area_cm2_pred") is not None
        and row.get("area_cm2_gt") is not None
    ]
    ceiling = values("label_ceiling_dice")
    student_sam2 = values("student_vs_sam2_dice")
    return {
        "n": len(rows),
        "dice": dice["mean"],
        "dice_median": dice["median"],
        "iou": iou["mean"],
        "iou_median": iou["median"],
        "precision": precision["mean"],
        "recall": recall["mean"],
        "area_abs_pct_error_median": abs_error["median"],
        "area_abs_pct_error_p90": abs_error["p90"],
        "area_pct_error_signed_mean": signed["mean"],
        "area_cm2_mae": float(np.mean(cm2_pairs)) if cm2_pairs else 0.0,
        "no_marker": sum(1 for row in rows if not row.get("marker")),
        "label_ceiling_dice": float(np.mean(ceiling)) if ceiling else 0.0,
        "student_vs_sam2_dice": float(np.mean(student_sam2)) if student_sam2 else 0.0,
    }


def evaluate_split(
    model,
    samples: Sequence[Sample],
    *,
    image_size: tuple[int, int],
    threshold: float,
    device: str,
    amp: bool,
    sam2_masks: Path | None = None,
    limit: int = 0,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Evaluate one split at native resolution.

    Args:
        model: Segmentation model.
        samples: Split samples.
        image_size: Model input ``(H, W)``.
        threshold: Probability threshold.
        device: Torch device string.
        amp: Enable bf16 autocast on CUDA.
        sam2_masks: Directory of SAM2 PNG masks for the ceiling metric.
        limit: Evaluate only the first N samples when positive.

    Returns:
        ``(summary, per_frame_rows)``.

    Raises:
        ValueError: If the split is empty or a label has zero area.
        FileNotFoundError: If an image cannot be read.
    """
    selected = list(samples[:limit]) if limit > 0 else list(samples)
    if not selected:
        raise ValueError("empty split")
    rows: list[dict[str, object]] = []
    for sample in selected:
        image = cv2.imread(str(sample.image_path))
        if image is None:
            raise FileNotFoundError(f"cannot read image: {sample.image_path}")
        height, width = image.shape[:2]
        native = parse_yolo_seg_label(sample.label_path, width=width, height=height)
        pred = predict_mask(
            model,
            image,
            image_size=image_size,
            threshold=threshold,
            device=device,
            amp=amp,
        )
        rows.append(
            _frame_row(
                sample,
                pred,
                native,
                ppm=px_per_mm(image),
                sam2_masks=sam2_masks,
            )
        )
    return _aggregate(rows), rows


def gate_verdict(
    summary: Mapping[str, Mapping[str, object]],
    gate: Mapping[str, float],
) -> tuple[str, list[str]]:
    """Apply the frozen promotion thresholds.

    Args:
        summary: Mapping ``split -> summary``; ``test`` is required.
        gate: Threshold mapping from ``configs/train.yaml``.

    Returns:
        ``("promote", [])`` or ``("rollback", reasons)``.

    Raises:
        ValueError: If the test summary is missing.
    """
    test = summary.get("test")
    if not test:
        raise ValueError("test split summary required")
    failures: list[str] = []
    checks = (
        ("dice", "min_test_dice"),
        ("iou", "min_test_iou"),
        ("recall", "min_test_recall"),
        ("area_abs_pct_error_median", "max_area_abs_pct_error_median"),
        ("area_abs_pct_error_p90", "max_area_abs_pct_error_p90"),
    )
    for field, limit_key in checks:
        value = float(test[field])
        limit = float(gate[limit_key])
        if limit_key.startswith("min_") and value < limit:
            failures.append(f"{field} {value:.4f} < {limit}")
        if limit_key.startswith("max_") and value > limit:
            failures.append(f"{field} {value:.4f} > {limit}")
    val = summary.get("val")
    if val and float(val["dice"]) < float(gate["min_val_dice"]):
        failures.append(f"val_dice {float(val['dice']):.4f} < {gate['min_val_dice']}")
    return ("rollback", failures) if failures else ("promote", [])
