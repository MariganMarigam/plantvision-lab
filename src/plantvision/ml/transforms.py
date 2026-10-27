"""Blurple-safe albumentations pipelines (geometry + exposure only, no hue)."""

from __future__ import annotations

from dataclasses import dataclass

MEAN: tuple[float, float, float] = (0.485, 0.456, 0.406)
STD: tuple[float, float, float] = (0.229, 0.224, 0.225)


@dataclass(frozen=True)
class AugConfig:
    """Augmentation strengths; the only photometric ops are exposure-like."""

    hflip_p: float = 0.5
    vflip_p: float = 0.3
    shift_limit: float = 0.05
    scale_limit: float = 0.1
    rotate_limit: float = 15.0
    brightness_limit: float = 0.2
    contrast_limit: float = 0.2
    gamma_limit: tuple[int, int] = (80, 120)
    blur_p: float = 0.15
    image_size: tuple[int, int] = (288, 512)


def validate_aug_config(cfg: AugConfig) -> None:
    """Validate augmentation strengths and model input size.

    Args:
        cfg: Augmentation configuration.

    Raises:
        ValueError: If any probability is outside ``[0, 1]``, a limit is out
            of range, the gamma range is inverted, or ``image_size`` is not a
            pair of positive multiples of 32 (SegFormer decoder requirement).
    """
    for name in ("hflip_p", "vflip_p", "blur_p"):
        value = float(getattr(cfg, name))
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1], got {value}")
    if not 0.0 <= cfg.shift_limit <= 0.2:
        raise ValueError(f"shift_limit must be in [0, 0.2], got {cfg.shift_limit}")
    if not 0.0 <= cfg.scale_limit <= 0.3:
        raise ValueError(f"scale_limit must be in [0, 0.3], got {cfg.scale_limit}")
    if not 0.0 <= cfg.rotate_limit <= 45.0:
        raise ValueError(f"rotate_limit must be in [0, 45], got {cfg.rotate_limit}")
    gamma_low, gamma_high = cfg.gamma_limit
    if not 80 <= gamma_low < gamma_high <= 120:
        raise ValueError(
            f"gamma_limit must satisfy 80 <= low < high <= 120, got {cfg.gamma_limit}"
        )
    height, width = cfg.image_size
    if height < 32 or width < 32 or height % 32 or width % 32:
        raise ValueError(
            f"image_size must be positive multiples of 32, got {cfg.image_size}"
        )


def build_train_transform(cfg: AugConfig) -> "object":
    """Build the training pipeline (geometry, exposure, resize, normalize).

    Args:
        cfg: Augmentation configuration.

    Returns:
        An ``albumentations.Compose`` taking ``image=`` (RGB) and ``mask=``.

    Raises:
        ImportError: If albumentations/OpenCV is not installed.
    """
    albumentations, cv2, to_tensor = _imports()
    height, width = cfg.image_size
    return albumentations.Compose(
        [
            albumentations.HorizontalFlip(p=cfg.hflip_p),
            albumentations.VerticalFlip(p=cfg.vflip_p),
            albumentations.ShiftScaleRotate(
                shift_limit=cfg.shift_limit,
                scale_limit=cfg.scale_limit,
                rotate_limit=cfg.rotate_limit,
                interpolation=cv2.INTER_LINEAR,
                border_mode=cv2.BORDER_CONSTANT,
                value=0,
                mask_value=0,
                mask_interpolation=cv2.INTER_NEAREST,
                p=0.5,
            ),
            albumentations.RandomBrightnessContrast(
                brightness_limit=cfg.brightness_limit,
                contrast_limit=cfg.contrast_limit,
                p=0.5,
            ),
            albumentations.RandomGamma(gamma_limit=cfg.gamma_limit, p=0.3),
            albumentations.GaussianBlur(blur_limit=(3, 5), p=cfg.blur_p),
            albumentations.Resize(
                height,
                width,
                interpolation=cv2.INTER_LINEAR,
                mask_interpolation=cv2.INTER_NEAREST,
            ),
            albumentations.Normalize(mean=MEAN, std=STD, max_pixel_value=255.0),
            to_tensor(),
        ]
    )


def build_eval_transform(image_size: tuple[int, int]) -> "object":
    """Build the deterministic evaluation pipeline.

    Args:
        image_size: Target ``(H, W)``.

    Returns:
        An ``albumentations.Compose`` with resize, normalize, and tensorize.

    Raises:
        ImportError: If albumentations/OpenCV is not installed.
    """
    albumentations, cv2, to_tensor = _imports()
    height, width = image_size
    return albumentations.Compose(
        [
            albumentations.Resize(
                height,
                width,
                interpolation=cv2.INTER_LINEAR,
                mask_interpolation=cv2.INTER_NEAREST,
            ),
            albumentations.Normalize(mean=MEAN, std=STD, max_pixel_value=255.0),
            to_tensor(),
        ]
    )


def _imports() -> tuple[object, object, object]:
    """Import albumentations, OpenCV, and ``ToTensorV2`` lazily.

    Raises:
        ImportError: If the ML extras are missing.
    """
    try:
        import albumentations
        import cv2
        from albumentations.pytorch import ToTensorV2
    except ImportError as exc:  # pragma: no cover - exercised only without extras
        raise ImportError("install requirements-ml.txt") from exc
    return albumentations, cv2, ToTensorV2
