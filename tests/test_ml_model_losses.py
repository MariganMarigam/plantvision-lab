"""Model, checkpoint, loss, and single-epoch tests (torch-gated)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from plantvision.ml.losses import bce_dice_loss, hard_dice
from plantvision.ml.model import (
    ModelConfig,
    build_model,
    count_parameters,
    load_checkpoint,
    save_checkpoint,
    sha256_file,
)
from plantvision.ml.train import train_one_epoch

LOSS_CFG = {"bce_weight": 0.5, "dice_weight": 0.5, "dice_eps": 1.0}


def _target() -> "torch.Tensor":
    """A small binary target with one foreground square per image."""
    target = torch.zeros(2, 1, 64, 64)
    target[:, :, 10:30, 10:30] = 1.0
    return target


def test_model_forward_shape_and_params() -> None:
    """SegFormer-b0 forwards (2,3,512,288) -> (2,1,512,288) with b0 size."""
    model = build_model(ModelConfig(encoder_weights=None))
    parameters = count_parameters(model)
    assert 3.4e6 <= parameters <= 4.0e6, f"unexpected parameter count: {parameters}"
    with torch.no_grad():
        logits = model(torch.zeros(2, 3, 512, 288))
    assert tuple(logits.shape) == (2, 1, 512, 288)


def test_checkpoint_roundtrip(tmp_path: Path) -> None:
    """State dict and metadata survive a save/load roundtrip."""
    model = build_model(ModelConfig(encoder_weights=None))
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    path = tmp_path / "checkpoint.pt"
    save_checkpoint(
        path,
        model,
        optimizer,
        None,
        epoch=3,
        best_val_dice=0.75,
        meta={"model_config": {"arch": "segformer"}, "image_size": [512, 288]},
    )
    assert len(sha256_file(path)) == 64
    restored = build_model(ModelConfig(encoder_weights=None))
    state = load_checkpoint(
        path, restored, torch.optim.AdamW(restored.parameters(), lr=1e-4)
    )
    assert state["epoch"] == 3
    assert state["best_val_dice"] == pytest.approx(0.75)
    assert state["meta"]["image_size"] == [512, 288]


def test_bce_dice_bounds() -> None:
    """Near-perfect logits give a small loss, inverted logits a large one."""
    target = _target()
    perfect = torch.where(target > 0.5, 20.0, -20.0)
    inverted = torch.where(target > 0.5, -20.0, 20.0)
    assert float(bce_dice_loss(perfect, target)) < 0.05
    assert float(bce_dice_loss(inverted, target)) > 0.9
    background = torch.zeros(2, 1, 8, 8)
    # Plan correction: BCE(0,0)=ln2 and the soft-Dice term is 1 - 1/33 for this batch,
    # so the all-zero case is 0.831422, not the "<0.05" the plan's verify snippet claimed.
    assert float(bce_dice_loss(background, background)) == pytest.approx(
        0.831422, abs=1e-5
    )
    with pytest.raises(ValueError):
        bce_dice_loss(background, background, dice_eps=0.0)


def test_hard_dice_perfect() -> None:
    """Confident matching logits score a hard Dice of 1."""
    target = _target()
    perfect = torch.where(target > 0.5, 20.0, -20.0)
    assert hard_dice(perfect, target) == pytest.approx(1.0)


def test_train_one_epoch_tiny() -> None:
    """One synthetic batch updates parameters and yields finite metrics."""
    model = build_model(ModelConfig(encoder_weights=None))
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    image = torch.rand(2, 3, 64, 64)
    mask = torch.zeros(2, 1, 64, 64)
    mask[:, :, 16:48, 16:48] = 1.0
    before = next(model.parameters()).detach().clone()
    stats = train_one_epoch(
        model,
        [{"image": image, "mask": mask}],
        optimizer,
        "cpu",
        loss_cfg=LOSS_CFG,
        amp=False,
        grad_clip=1.0,
    )
    assert math.isfinite(stats["loss"])
    assert 0.0 <= stats["dice"] <= 1.0
    assert not torch.equal(before, next(model.parameters()).detach())
