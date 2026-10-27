"""Training configuration, loop, AMP handling, and run artifacts.

Torch is imported inside the functions that need it so that importing this
module (and ``plantvision.perception``) never loads torch.
"""

from __future__ import annotations

import dataclasses
import json
import random
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml

from plantvision.ml.dataset import (
    SPLITS,
    YoloSegDataset,
    assert_no_leakage,
    discover_samples,
    load_manifest,
)
from plantvision.ml.losses import bce_dice_loss
from plantvision.ml.model import (
    ModelConfig,
    build_model,
    count_parameters,
    load_checkpoint,
    save_checkpoint,
    sha256_file,
)
from plantvision.ml.transforms import (
    AugConfig,
    build_eval_transform,
    build_train_transform,
    validate_aug_config,
)

REQUIRED_KEYS: tuple[str, ...] = (
    "seed",
    "device",
    "amp",
    "amp_dtype",
    "epochs",
    "batch_size",
    "num_workers",
    "lr",
    "weight_decay",
    "warmup_epochs",
    "grad_clip_norm",
    "image_size",
    "threshold",
    "crop_id",
    "model_id",
    "model",
    "loss",
    "dataset",
    "augmentation",
    "checkpoint",
    "registry",
    "gate",
)

HISTORY_COLUMNS: tuple[str, ...] = (
    "epoch",
    "train_loss",
    "val_loss",
    "val_dice",
    "lr",
    "seconds",
    "peak_vram_gb",
)


@dataclass(frozen=True)
class TrainConfig:
    """Validated training configuration with repo-absolute paths."""

    seed: int
    device: str
    amp: bool
    amp_dtype: str
    epochs: int
    batch_size: int
    num_workers: int
    lr: float
    weight_decay: float
    warmup_epochs: int
    grad_clip_norm: float
    image_size: tuple[int, int]
    threshold: float
    crop_id: str
    model_id: str
    model: dict
    loss: dict
    dataset: dict
    augmentation: dict
    checkpoint: dict
    registry: dict
    gate: dict
    repo_root: Path


class _NonFiniteLoss(RuntimeError):
    """Raised by :func:`train_one_epoch` when a batch loss is not finite."""

    def __init__(self, step: int) -> None:
        super().__init__(f"non-finite loss at step {step}")
        self.step = step


def load_train_config(path: str | Path) -> TrainConfig:
    """Load and validate ``configs/train.yaml``.

    Args:
        path: YAML configuration path.

    Returns:
        Validated configuration; dataset/checkpoint/registry paths are absolute.

    Raises:
        ValueError: Malformed YAML, missing keys, or an out-of-range value.
        FileNotFoundError: If ``path`` does not exist.
    """
    config_path = Path(path).resolve()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"config {path} must be a mapping")
    missing = [key for key in REQUIRED_KEYS if key not in raw]
    if missing:
        raise ValueError(f"config {path} missing keys: {missing}")
    _validate_scalars(raw, path)
    repo_root = config_path.parent.parent
    dataset = _resolved_dataset(raw["dataset"], repo_root)
    checkpoint = dict(raw["checkpoint"])
    checkpoint["dir"] = str((repo_root / str(checkpoint["dir"])).resolve())
    registry = dict(raw["registry"])
    registry["path"] = str((repo_root / str(registry["path"])).resolve())
    return TrainConfig(
        seed=int(raw["seed"]),
        device=str(raw["device"]),
        amp=bool(raw["amp"]),
        amp_dtype=str(raw["amp_dtype"]),
        epochs=int(raw["epochs"]),
        batch_size=int(raw["batch_size"]),
        num_workers=int(raw["num_workers"]),
        lr=float(raw["lr"]),
        weight_decay=float(raw["weight_decay"]),
        warmup_epochs=int(raw["warmup_epochs"]),
        grad_clip_norm=float(raw["grad_clip_norm"]),
        image_size=_int_pair(raw["image_size"], "image_size", path),
        threshold=float(raw["threshold"]),
        crop_id=str(raw["crop_id"]).strip(),
        model_id=str(raw["model_id"]),
        model=dict(raw["model"]),
        loss=dict(raw["loss"]),
        dataset=dataset,
        augmentation=_augmentation(raw["augmentation"]),
        checkpoint=checkpoint,
        registry=registry,
        gate=dict(raw["gate"]),
        repo_root=repo_root,
    )


def _validate_scalars(raw: Mapping[str, Any], path: Path) -> None:
    """Validate the scalar/structural config values."""
    model = dict(raw["model"])
    if model.get("arch") != "segformer":
        raise ValueError(f"model.arch must be 'segformer', got {model.get('arch')!r}")
    if model.get("classes") != 1:
        raise ValueError(f"model.classes must be 1, got {model.get('classes')!r}")
    image_size = _int_pair(raw["image_size"], "image_size", path)
    if any(size <= 0 or size % 32 for size in image_size):
        raise ValueError(f"image_size must be positive multiples of 32, got {image_size}")
    if not 0.0 < float(raw["threshold"]) < 1.0:
        raise ValueError(f"threshold must be in (0, 1), got {raw['threshold']}")
    if int(raw["batch_size"]) < 1:
        raise ValueError(f"batch_size must be >= 1, got {raw['batch_size']}")
    if int(raw["epochs"]) < 1:
        raise ValueError(f"epochs must be >= 1, got {raw['epochs']}")
    if float(raw["lr"]) <= 0:
        raise ValueError(f"lr must be > 0, got {raw['lr']}")
    if int(raw["num_workers"]) < 0:
        raise ValueError(f"num_workers must be >= 0, got {raw['num_workers']}")
    if int(raw["warmup_epochs"]) >= int(raw["epochs"]):
        raise ValueError(
            f"warmup_epochs ({raw['warmup_epochs']}) must be < epochs ({raw['epochs']})"
        )
    if dict(raw["checkpoint"]).get("monitor") != "val_dice":
        raise ValueError("checkpoint.monitor must be 'val_dice'")
    if not str(raw["crop_id"]).strip():
        raise ValueError("crop_id must be non-empty")


def _int_pair(value: Any, name: str, path: Path) -> tuple[int, int]:
    """Cast a two-element sequence to ``tuple[int, int]``."""
    try:
        first, second = value
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a pair in {path}, got {value!r}") from exc
    return int(first), int(second)


def _resolved_dataset(raw: Any, repo_root: Path) -> dict:
    """Resolve dataset paths against the repo root and cast the size pair."""
    dataset = dict(raw)
    for key in ("root", "manifest", "sam2_masks"):
        dataset[key] = str((repo_root / str(dataset[key])).resolve())
    dataset["expected_image_size"] = _int_pair(
        dataset["expected_image_size"], "dataset.expected_image_size", repo_root
    )
    return dataset


def _augmentation(raw: Any) -> dict:
    """Copy the augmentation block, casting ``gamma_limit`` to a tuple."""
    augmentation = dict(raw)
    if "gamma_limit" in augmentation:
        low, high = augmentation["gamma_limit"]
        augmentation["gamma_limit"] = (int(low), int(high))
    return augmentation


def seed_everything(seed: int) -> None:
    """Seed Python, NumPy, and torch (CPU + CUDA).

    Args:
        seed: Seed value applied to every RNG.
    """
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = True


def _worker_init(worker_id: int) -> None:
    """Seed NumPy and ``random`` in a DataLoader worker."""
    import torch

    seed = torch.initial_seed() % 2**32
    np.random.seed(seed)
    random.seed(seed)


def _resolve_device(device: str) -> str:
    """Resolve ``auto`` to CUDA when available.

    Args:
        device: ``auto``, ``cuda``, or ``cpu``.

    Returns:
        A concrete device string.

    Raises:
        ValueError: If CUDA is requested but unavailable.
    """
    import torch

    if device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if device.startswith("cuda") and not torch.cuda.is_available():
        raise ValueError("CUDA requested but not available")
    return device


def _accumulate_counts(
    logits: "torch.Tensor", target: "torch.Tensor", threshold: float
) -> tuple[float, float, float]:
    """Return ``(tp, fp, fn)`` pixel counts for one batch."""
    import torch

    pred = torch.sigmoid(logits.float()) >= threshold
    truth = target.bool()
    tp = float((pred & truth).sum().item())
    fp = float((pred & ~truth).sum().item())
    fn = float((~pred & truth).sum().item())
    return tp, fp, fn


def train_one_epoch(
    model,
    loader,
    optimizer,
    device,
    *,
    loss_cfg: dict,
    amp: bool,
    grad_clip: float,
) -> dict[str, float]:
    """Train one epoch over ``loader``.

    Args:
        model: Segmentation model.
        loader: Batches with ``image`` and ``mask`` at model resolution.
        optimizer: Optimizer.
        device: Torch device string.
        loss_cfg: Keyword arguments for :func:`bce_dice_loss`.
        amp: Enable bf16 autocast on CUDA.
        grad_clip: Gradient-norm clip value.

    Returns:
        ``{"loss": mean batch loss, "dice": global hard Dice}``.

    Raises:
        _NonFiniteLoss: If a batch loss is not finite.
        ValueError: If the loader yields no batch.
    """
    import torch

    use_cuda = str(device).startswith("cuda")
    model.train()
    total_loss, batches, tp, fp, fn = 0.0, 0, 0.0, 0.0, 0.0
    for step, batch in enumerate(loader):
        image = batch["image"].to(device, non_blocking=use_cuda)
        mask = batch["mask"].to(device, non_blocking=use_cuda)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(
            device_type="cuda", dtype=torch.bfloat16, enabled=amp and use_cuda
        ):
            logits = model(image)
            loss = bce_dice_loss(logits, mask, **loss_cfg)
        if not bool(torch.isfinite(loss)):
            raise _NonFiniteLoss(step)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
        optimizer.step()
        total_loss += float(loss.detach())
        batches += 1
        batch_tp, batch_fp, batch_fn = _accumulate_counts(logits.detach(), mask, 0.5)
        tp, fp, fn = tp + batch_tp, fp + batch_fp, fn + batch_fn
    if batches == 0:
        raise ValueError("empty training loader")
    return {"loss": total_loss / batches, "dice": 2 * tp / (2 * tp + fp + fn + 1e-9)}


def validate(
    model,
    loader,
    device,
    *,
    loss_cfg: dict,
    amp: bool,
    threshold: float,
) -> dict[str, float]:
    """Validate one epoch at native mask resolution.

    Args:
        model: Segmentation model.
        loader: Batches with ``image``, ``mask``, and ``mask_native``.
        device: Torch device string.
        loss_cfg: Keyword arguments for :func:`bce_dice_loss`.
        amp: Enable bf16 autocast on CUDA.
        threshold: Probability threshold used for the native-resolution mask.

    Returns:
        ``{"loss": mean loss, "dice": native Dice, "n": frame count}``.

    Raises:
        ValueError: If the loader yields no batch.
    """
    import torch
    import torch.nn.functional as functional

    use_cuda = str(device).startswith("cuda")
    model.eval()
    total_loss, batches, tp, fp, fn, count = 0.0, 0, 0.0, 0.0, 0.0, 0
    with torch.no_grad():
        for batch in loader:
            image = batch["image"].to(device, non_blocking=use_cuda)
            mask = batch["mask"].to(device, non_blocking=use_cuda)
            native = batch["mask_native"].to(device, non_blocking=use_cuda)
            with torch.autocast(
                device_type="cuda", dtype=torch.bfloat16, enabled=amp and use_cuda
            ):
                logits = model(image)
                loss = bce_dice_loss(logits, mask, **loss_cfg)
            total_loss += float(loss)
            batches += 1
            upsampled = functional.interpolate(
                logits.float(),
                size=native.shape[-2:],
                mode="bilinear",
                align_corners=False,
            )
            batch_tp, batch_fp, batch_fn = _accumulate_counts(
                upsampled, native, threshold
            )
            tp, fp, fn = tp + batch_tp, fp + batch_fp, fn + batch_fn
            count += int(image.shape[0])
    if batches == 0:
        raise ValueError("empty validation loader")
    return {
        "loss": total_loss / batches,
        "dice": 2 * tp / (2 * tp + fp + fn + 1e-9),
        "n": float(count),
    }


def dry_run(
    cfg: TrainConfig,
    *,
    dataset_root: Path | None = None,
    batch_size: int | None = None,
) -> dict[str, object]:
    """Run one forward+backward pass without optimizer step or file writes.

    Args:
        cfg: Training configuration.
        dataset_root: Override of ``cfg.dataset["root"]``.
        batch_size: Override of ``cfg.batch_size``.

    Returns:
        Shapes, parameter count, and peak VRAM of the probe batch.

    Raises:
        ValueError: If a split is empty or the batch is not produced.
    """
    import torch
    from torch.utils.data import DataLoader

    seed_everything(cfg.seed)
    root = Path(dataset_root) if dataset_root is not None else Path(cfg.dataset["root"])
    manifest = load_manifest(Path(cfg.dataset["manifest"]))
    train_samples = discover_samples(root, "train", manifest)
    val_samples = discover_samples(root, "val", manifest)
    if not train_samples or not val_samples:
        raise ValueError("train and val splits must be non-empty")
    aug = AugConfig(**cfg.augmentation, image_size=cfg.image_size)
    validate_aug_config(aug)
    dataset = YoloSegDataset(
        train_samples,
        image_size=cfg.image_size,
        transform=build_train_transform(aug),
        expected_image_size=tuple(cfg.dataset["expected_image_size"]),
    )
    loader = DataLoader(
        dataset, batch_size=batch_size or cfg.batch_size, shuffle=False, num_workers=0
    )
    batch = next(iter(loader), None)
    if batch is None:
        raise ValueError("dry run produced no batch")
    device = _resolve_device(cfg.device)
    use_cuda = device.startswith("cuda")
    model = build_model(ModelConfig(**cfg.model)).to(device)
    image = batch["image"].to(device)
    mask = batch["mask"].to(device)
    if use_cuda:
        torch.cuda.reset_peak_memory_stats()
    model.train()
    with torch.autocast(
        device_type="cuda", dtype=torch.bfloat16, enabled=cfg.amp and use_cuda
    ):
        logits = model(image)
        loss = bce_dice_loss(logits, mask, **cfg.loss)
    loss.backward()
    peak = torch.cuda.max_memory_allocated() / 1e9 if use_cuda else 0.0
    return {
        "image_shape": list(image.shape),
        "mask_shape": list(mask.shape),
        "logits_shape": list(logits.shape),
        "parameters": count_parameters(model),
        "peak_vram_gb": round(float(peak), 3),
        "batch_size": int(image.shape[0]),
    }


def _build_loaders(
    train_dataset: YoloSegDataset,
    val_dataset: YoloSegDataset,
    batch_size: int,
    cfg: TrainConfig,
    use_cuda: bool,
) -> tuple[object, object]:
    """Build seeded train/val DataLoaders."""
    import torch
    from torch.utils.data import DataLoader

    generator = torch.Generator()
    generator.manual_seed(cfg.seed)
    drop_last = len(train_dataset) >= batch_size
    if not drop_last:
        print("[train] warning: train samples < batch size; drop_last=False")
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        drop_last=drop_last,
        num_workers=cfg.num_workers,
        pin_memory=use_cuda,
        worker_init_fn=_worker_init,
        generator=generator,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=cfg.num_workers,
        pin_memory=use_cuda,
        worker_init_fn=_worker_init,
    )
    return train_loader, val_loader


def _build_scheduler(optimizer, warmup: int, epochs: int):
    """Build the linear-warmup + cosine schedule."""
    import torch

    warm = torch.optim.lr_scheduler.LinearLR(optimizer, total_iters=max(1, warmup))
    cosine = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=max(1, epochs - warmup), eta_min=1e-6
    )
    return torch.optim.lr_scheduler.SequentialLR(
        optimizer, schedulers=[warm, cosine], milestones=[max(1, warmup)]
    )


def _jsonable(value: Any) -> Any:
    """Convert dataclasses, ``Path``, and tuples to JSON-safe values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write pretty JSON with a UTF-8 encoding."""
    path.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8"
    )


def _git_sha(repo_root: Path) -> str:
    """Return the current git HEAD, or ``"unknown"``."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _checkpoint_meta(
    cfg: TrainConfig,
    *,
    manifest_sha: str,
    counts: Mapping[str, int],
    git_sha: str,
    device: str,
) -> dict[str, Any]:
    """Build the metadata stored in every checkpoint."""
    import torch

    cuda_device = torch.cuda.get_device_name(0) if device.startswith("cuda") else "cpu"
    return {
        "model_config": dataclasses.asdict(ModelConfig(**cfg.model)),
        "train_config": _jsonable(cfg),
        "image_size": list(cfg.image_size),
        "threshold": cfg.threshold,
        "crop_id": cfg.crop_id,
        "model_id": cfg.model_id,
        "dataset": {"manifest_sha256": manifest_sha, "splits": dict(counts)},
        "git_sha": git_sha,
        "torch_version": torch.__version__,
        "cuda_device": cuda_device,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _append_history(path: Path, row: Mapping[str, Any]) -> None:
    """Append one epoch row to ``history.csv``, writing the header first."""
    line = ",".join(_format_csv(row[column]) for column in HISTORY_COLUMNS)
    if not path.exists():
        header = ",".join(HISTORY_COLUMNS) + "\n"
        path.write_text(header + line + "\n", encoding="utf-8")
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _format_csv(value: Any) -> str:
    """Format one CSV cell (six decimals for floats)."""
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _metrics_payload(
    history: Sequence[Mapping[str, Any]],
    *,
    best_epoch: int,
    best_val_dice: float,
    peak_vram_gb: float,
    train_seconds: float,
    final_batch_size: int,
    stopped_early: bool,
) -> dict[str, Any]:
    """Build the ``metrics.json`` payload."""
    return {
        "best_epoch": best_epoch,
        "best_val_dice": best_val_dice,
        "epochs_run": len(history),
        "stopped_early": stopped_early,
        "history": list(history),
        "peak_vram_gb": peak_vram_gb,
        "train_seconds": train_seconds,
        "final_batch_size": final_batch_size,
    }


def train(
    cfg: TrainConfig,
    *,
    dataset_root: Path | None = None,
    out_dir: Path | None = None,
    run_id: str = "",
    epochs: int | None = None,
    batch_size: int | None = None,
    limit_train: int = 0,
    limit_val: int = 0,
    resume: Path | None = None,
) -> dict[str, object]:
    """Train, checkpoint, and record one run.

    Args:
        cfg: Validated training configuration.
        dataset_root: Override of ``cfg.dataset["root"]``.
        out_dir: Root of ``<crop_id>/<run_id>``; defaults to ``checkpoint.dir``.
        run_id: Run directory name (``[A-Za-z0-9._-]+``).
        epochs: Override of ``cfg.epochs``.
        batch_size: Override of ``cfg.batch_size``.
        limit_train: Use only the first N train samples (0 = all).
        limit_val: Use only the first N val samples (0 = all).
        resume: Checkpoint to resume from.

    Returns:
        Summary dict written to ``metrics.json`` plus ``run_dir``.

    Raises:
        ValueError: Invalid run id, empty splits, or empty loader.
        FileNotFoundError: Missing manifest or dataset directory.
        RuntimeError: Non-finite loss or unrecoverable OOM.
    """
    import torch

    if not run_id or not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise ValueError(f"invalid run_id: {run_id!r}")
    total_epochs = int(epochs) if epochs is not None else cfg.epochs
    if total_epochs < 1:
        raise ValueError(f"epochs must be >= 1, got {total_epochs}")
    current_batch = int(batch_size) if batch_size is not None else cfg.batch_size
    seed_everything(cfg.seed)
    root = Path(dataset_root) if dataset_root is not None else Path(cfg.dataset["root"])
    manifest_path = Path(cfg.dataset["manifest"])
    manifest = load_manifest(manifest_path)
    splits = {split: discover_samples(root, split, manifest) for split in SPLITS}
    assert_no_leakage(splits)
    train_samples = splits["train"][:limit_train] if limit_train > 0 else splits["train"]
    val_samples = splits["val"][:limit_val] if limit_val > 0 else splits["val"]
    if not train_samples:
        raise ValueError("no samples for split 'train'")
    if not val_samples:
        raise ValueError("no samples for split 'val'")
    aug = AugConfig(**cfg.augmentation, image_size=cfg.image_size)
    validate_aug_config(aug)
    device = _resolve_device(cfg.device)
    use_cuda = device.startswith("cuda")
    if cfg.amp and not use_cuda:
        print("[train] CUDA unavailable: AMP disabled")
    train_dataset = YoloSegDataset(
        train_samples,
        image_size=cfg.image_size,
        transform=build_train_transform(aug),
        expected_image_size=tuple(cfg.dataset["expected_image_size"]),
    )
    val_dataset = YoloSegDataset(
        val_samples,
        image_size=cfg.image_size,
        transform=build_eval_transform(cfg.image_size),
        return_native_mask=True,
        expected_image_size=tuple(cfg.dataset["expected_image_size"]),
    )
    model = build_model(ModelConfig(**cfg.model)).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay
    )
    warmup = min(cfg.warmup_epochs, max(1, total_epochs - 1))
    scheduler = _build_scheduler(optimizer, warmup, total_epochs)
    print(f"[train] warmup epochs: {warmup}")
    start_epoch, best_val_dice, best_epoch = 0, -1.0, 0
    if resume is not None:
        state = load_checkpoint(Path(resume), model, optimizer, scheduler)
        start_epoch = int(state["epoch"]) + 1
        best_val_dice = float(state["best_val_dice"])
        best_epoch = start_epoch - 1
    run_root = Path(out_dir) if out_dir is not None else Path(cfg.checkpoint["dir"])
    run_path = run_root / cfg.crop_id / run_id
    weights_dir = run_path / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    manifest_sha = sha256_file(manifest_path)
    counts = {split: len(samples) for split, samples in splits.items()}
    git_sha = _git_sha(cfg.repo_root)
    meta = _checkpoint_meta(
        cfg, manifest_sha=manifest_sha, counts=counts, git_sha=git_sha, device=device
    )
    (run_path / "config.yaml").write_text(
        yaml.safe_dump(_jsonable(cfg), sort_keys=False), encoding="utf-8"
    )
    run_info: dict[str, Any] = {
        "run_id": run_id,
        "crop_id": cfg.crop_id,
        "model_id": cfg.model_id,
        "git_sha": git_sha,
        "manifest_sha256": manifest_sha,
        "splits": counts,
        "epochs_requested": total_epochs,
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "device": device,
        "seed": cfg.seed,
    }
    _write_json(run_path / "run.json", run_info)
    if use_cuda:
        torch.cuda.reset_peak_memory_stats()
    history: list[dict[str, Any]] = []
    train_loader, val_loader = _build_loaders(
        train_dataset, val_dataset, current_batch, cfg, use_cuda
    )
    started = time.perf_counter()
    stopped_early, patience, oom_halvings = False, 0, 0
    metrics_path = run_path / "metrics.json"
    for epoch in range(start_epoch, total_epochs):
        epoch_started = time.perf_counter()
        while True:
            try:
                train_stats = train_one_epoch(
                    model,
                    train_loader,
                    optimizer,
                    device,
                    loss_cfg=cfg.loss,
                    amp=cfg.amp and use_cuda,
                    grad_clip=cfg.grad_clip_norm,
                )
                break
            except torch.cuda.OutOfMemoryError:
                if oom_halvings >= 2 or current_batch <= 2:
                    raise
                oom_halvings += 1
                current_batch //= 2
                torch.cuda.empty_cache()
                print(f"[train] OOM: batch size -> {current_batch}")
                train_loader, val_loader = _build_loaders(
                    train_dataset, val_dataset, current_batch, cfg, use_cuda
                )
        val_stats = validate(
            model,
            val_loader,
            device,
            loss_cfg=cfg.loss,
            amp=cfg.amp and use_cuda,
            threshold=cfg.threshold,
        )
        scheduler.step()
        seconds = time.perf_counter() - epoch_started
        peak = torch.cuda.max_memory_allocated() / 1e9 if use_cuda else 0.0
        row = {
            "epoch": epoch + 1,
            "train_loss": train_stats["loss"],
            "val_loss": val_stats["loss"],
            "val_dice": val_stats["dice"],
            "lr": optimizer.param_groups[0]["lr"],
            "seconds": seconds,
            "peak_vram_gb": round(float(peak), 3),
        }
        history.append(row)
        _append_history(run_path / "history.csv", row)
        if val_stats["dice"] > best_val_dice + cfg.checkpoint["early_stop_min_delta"]:
            best_val_dice, best_epoch, patience = val_stats["dice"], epoch + 1, 0
            save_checkpoint(
                weights_dir / "best.pt",
                model,
                optimizer,
                scheduler,
                epoch=epoch,
                best_val_dice=best_val_dice,
                meta=meta,
            )
        else:
            patience += 1
        save_checkpoint(
            weights_dir / "last.pt",
            model,
            optimizer,
            scheduler,
            epoch=epoch,
            best_val_dice=best_val_dice,
            meta=meta,
        )
        elapsed = time.perf_counter() - started
        _write_json(
            metrics_path,
            _metrics_payload(
                history,
                best_epoch=best_epoch,
                best_val_dice=best_val_dice,
                peak_vram_gb=round(float(peak), 3),
                train_seconds=elapsed,
                final_batch_size=current_batch,
                stopped_early=stopped_early,
            ),
        )
        if patience >= cfg.checkpoint["early_stop_patience"]:
            stopped_early = True
            break
    elapsed = time.perf_counter() - started
    run_info.update(
        {
            "peak_vram_gb": round(
                float(torch.cuda.max_memory_allocated() / 1e9) if use_cuda else 0.0, 3
            ),
            "train_seconds": elapsed,
            "final_batch_size": current_batch,
            "oom_halvings": oom_halvings,
        }
    )
    _write_json(run_path / "run.json", run_info)
    summary = _metrics_payload(
        history,
        best_epoch=best_epoch,
        best_val_dice=best_val_dice,
        peak_vram_gb=run_info["peak_vram_gb"],
        train_seconds=elapsed,
        final_batch_size=current_batch,
        stopped_early=stopped_early,
    )
    _write_json(metrics_path, summary)
    return {"run_dir": str(run_path), **summary}
