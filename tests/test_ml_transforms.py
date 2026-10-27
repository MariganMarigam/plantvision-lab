"""Blurple-safe augmentation invariant tests."""

from __future__ import annotations

import random

import numpy as np
import pytest

from plantvision.ml.transforms import (
    AugConfig,
    build_eval_transform,
    build_train_transform,
    validate_aug_config,
)

FORBIDDEN_SUBSTRINGS = ("Hue", "HSV", "RGBShift", "ColorJitter", "Saturation")


def _sample() -> tuple[np.ndarray, np.ndarray]:
    """Random RGB image plus a binary mask at native portrait resolution."""
    rng = np.random.default_rng(7)
    image = rng.integers(0, 256, size=(1280, 720, 3), dtype=np.uint8)
    mask = (rng.random((1280, 720)) > 0.7).astype(np.uint8) * 255
    return image, mask


def test_mask_stays_binary() -> None:
    """Geometric/photometric ops never introduce mask values other than 0/255."""
    image, mask = _sample()
    transform = build_train_transform(AugConfig(image_size=(512, 288)))
    for _ in range(10):
        random.seed(0)
        np.random.seed(0)
        out = transform(image=image, mask=mask)
        result = out["mask"].numpy()
        assert result.shape == (512, 288)
        assert set(np.unique(result).tolist()) <= {0.0, 255.0}


def test_no_hue_or_saturation_ops() -> None:
    """No hue/saturation/colour-jitter op is part of the train pipeline."""
    names = [op.__class__.__name__ for op in build_train_transform(AugConfig()).transforms]
    for name in names:
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in name, f"{forbidden} op present: {name}"


def test_eval_transform_deterministic() -> None:
    """Two eval-transform calls on the same input produce identical tensors."""
    image, mask = _sample()
    transform = build_eval_transform((512, 288))
    random.seed(1)
    np.random.seed(1)
    first = transform(image=image, mask=mask)["image"].numpy()
    random.seed(999)
    np.random.seed(999)
    second = transform(image=image, mask=mask)["image"].numpy()
    assert np.array_equal(first, second)
    assert first.shape == (3, 512, 288)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"hflip_p": 1.1},
        {"rotate_limit": 90.0},
        {"image_size": (300, 512)},
        {"gamma_limit": (120, 80)},
    ],
    ids=["hflip-p", "rotate", "image-size", "gamma-order"],
)
def test_validate_aug_config_rejects(kwargs: dict) -> None:
    """Out-of-range augmentation values raise ValueError."""
    with pytest.raises(ValueError):
        validate_aug_config(AugConfig(**kwargs))
