"""BCE + Dice objective and hard-Dice accumulation."""

from __future__ import annotations


def bce_dice_loss(
    logits: "torch.Tensor",
    target: "torch.Tensor",
    *,
    bce_weight: float = 0.5,
    dice_weight: float = 0.5,
    dice_eps: float = 1.0,
) -> "torch.Tensor":
    """Weighted BCE-with-logits plus soft per-image Dice.

    Args:
        logits: ``[B, 1, H, W]`` raw logits.
        target: ``[B, 1, H, W]`` binary float targets.
        bce_weight: Weight of the BCE term.
        dice_weight: Weight of the Dice term.
        dice_eps: Smoothing constant; must be positive.

    Returns:
        Scalar loss tensor.

    Raises:
        ValueError: If ``dice_eps <= 0``.
    """
    import torch
    import torch.nn.functional as functional

    if dice_eps <= 0:
        raise ValueError(f"dice_eps must be > 0, got {dice_eps}")
    bce = functional.binary_cross_entropy_with_logits(logits, target)
    prob = torch.sigmoid(logits).float()
    truth = target.float()
    num = 2.0 * (prob * truth).sum(dim=(1, 2, 3)) + dice_eps
    den = prob.sum(dim=(1, 2, 3)) + truth.sum(dim=(1, 2, 3)) + dice_eps
    dice = 1.0 - (num / den).mean()
    return bce_weight * bce + dice_weight * dice


def hard_dice(
    logits: "torch.Tensor",
    target: "torch.Tensor",
    threshold: float = 0.5,
    eps: float = 1.0,
) -> float:
    """Thresholded (hard) Dice between sigmoid probabilities and targets.

    Args:
        logits: ``[B, 1, H, W]`` raw logits.
        target: ``[B, 1, H, W]`` binary targets.
        threshold: Probability threshold for the foreground class.
        eps: Smoothing constant.

    Returns:
        Dice in ``[0, 1]`` as a Python float.
    """
    import torch

    pred = torch.sigmoid(logits) >= threshold
    truth = target.bool()
    num = 2.0 * (pred & truth).sum().item() + eps
    den = pred.sum().item() + truth.sum().item() + eps
    return float(num / den)
