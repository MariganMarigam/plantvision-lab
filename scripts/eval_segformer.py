"""Evaluate a SegFormer student and optionally register it (P2)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import plantvision.ml.eval as evaluation
import plantvision.ml.train as training
from plantvision.ml.dataset import SPLITS, assert_no_leakage, discover_samples, load_manifest
from plantvision.ml.model import (
    ModelConfig,
    build_model,
    load_checkpoint,
    sha256_file,
)
from plantvision.ml.registry import (
    read_registry,
    repo_root,
    resolve_entry,
    write_registry_entry,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Evaluate a SegFormer student.")
    parser.add_argument("--config", default="configs/train.yaml")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--checkpoint", default="")
    source.add_argument("--model-id", default="")
    parser.add_argument("--split", choices=("val", "test", "all"), default="test")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default="")
    parser.add_argument("--write-gate", action="store_true")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--force-register", action="store_true")
    parser.add_argument("--sam2-masks", default="")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    args = parse_args(argv)
    usage_error = _usage_error(args)
    if usage_error:
        print(usage_error, file=sys.stderr)
        return 2
    try:
        cfg = training.load_train_config(args.config)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        resolved = _resolve_model(args, cfg)
        summary, frames = _evaluate(args, cfg, resolved)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    out_dir = _output_dir(args, cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    for split, rows in frames.items():
        _write_frames(out_dir / f"per_frame_{split}.csv", rows)
    _print_table(summary)
    if not args.write_gate:
        return 0
    verdict, reasons = evaluation.gate_verdict(summary, cfg.gate)
    payload = {
        "verdict": verdict,
        "reasons": reasons,
        "split": args.split,
        "checkpoint_sha256": sha256_file(resolved["checkpoint"]),
        "gate": cfg.gate,
    }
    (out_dir / "gate.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"VERDICT: {verdict}")
    for reason in reasons:
        print(f" - {reason}")
    if verdict != "promote":
        return 3
    if args.register:
        _register(args, cfg, resolved, summary)
    return 0


def _usage_error(args: argparse.Namespace) -> str | None:
    """Return a usage error message, or ``None`` when the flags are coherent."""
    if args.register:
        if not args.write_gate:
            return "--register requires --write-gate"
        if args.split != "test":
            return "--register requires --split test"
        if args.limit:
            return "--register requires --limit 0"
        if not args.checkpoint:
            return "--register requires --checkpoint"
    if args.write_gate and args.split not in ("test", "all"):
        return "--write-gate requires --split test or --split all"
    return None


def _device(name: str) -> str:
    """Resolve the evaluation device."""
    import torch

    if name == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if name.startswith("cuda") and not torch.cuda.is_available():
        raise ValueError("CUDA requested but not available")
    return name


def _checkpoint_meta(path: Path) -> Mapping[str, Any]:
    """Read checkpoint metadata without building the model."""
    import torch

    if not path.is_file():
        raise FileNotFoundError(f"checkpoint not found: {path}")
    payload = torch.load(path, map_location="cpu", weights_only=False)
    meta = payload.get("meta") or {}
    missing = [key for key in ("model_config", "image_size", "threshold") if key not in meta]
    if missing:
        raise ValueError(f"checkpoint meta missing keys: {missing}")
    return meta


def _resolve_model(
    args: argparse.Namespace, cfg: training.TrainConfig
) -> dict[str, Any]:
    """Build the model and read its sizing/threshold provenance."""
    device = _device(args.device)
    if args.checkpoint:
        checkpoint = Path(args.checkpoint)
        meta = _checkpoint_meta(checkpoint)
        config = ModelConfig(**meta["model_config"])
        model = build_model(config)
        state = load_checkpoint(checkpoint, model)
        return {
            "model": model.to(device).eval(),
            "device": device,
            "image_size": tuple(int(value) for value in meta["image_size"]),
            "threshold": float(meta["threshold"]),
            "checkpoint": checkpoint,
            "best_val_dice": float(state["best_val_dice"]),
            "config": config,
        }
    entry = resolve_entry(
        read_registry(Path(cfg.registry["path"])), args.model_id, cfg.crop_id
    )
    config = ModelConfig(
        arch=str(entry["arch"]),
        encoder=str(entry["encoder"]),
        encoder_weights=entry.get("encoder_weights"),  # type: ignore[arg-type]
        classes=int(entry["classes"]),
        decoder_channels=int(entry["decoder_channels"]),
    )
    checkpoint = Path(str(entry["checkpoint"]))
    if not checkpoint.is_absolute():
        checkpoint = repo_root() / checkpoint
    model = build_model(config)
    load_checkpoint(checkpoint, model)
    return {
        "model": model.to(device).eval(),
        "device": device,
        "image_size": tuple(int(value) for value in entry["image_size"]),
        "threshold": float(entry["threshold"]),
        "checkpoint": checkpoint,
        "best_val_dice": float(entry.get("val_dice", 0.0)),
        "config": config,
    }


def _evaluate(
    args: argparse.Namespace,
    cfg: training.TrainConfig,
    resolved: Mapping[str, Any],
) -> tuple[dict[str, dict[str, object]], dict[str, list[dict[str, object]]]]:
    """Evaluate the requested splits and return summaries plus frame rows."""
    manifest = load_manifest(Path(cfg.dataset["manifest"]))
    splits = {
        split: discover_samples(Path(cfg.dataset["root"]), split, manifest)
        for split in SPLITS
    }
    assert_no_leakage(splits)
    requested = list(SPLITS) if args.split == "all" else [args.split]
    sam2 = args.sam2_masks or cfg.dataset["sam2_masks"]
    sam2_path = Path(sam2) if sam2 else None
    amp = bool(cfg.amp) and str(resolved["device"]).startswith("cuda")
    summary: dict[str, dict[str, object]] = {}
    frames: dict[str, list[dict[str, object]]] = {}
    for split in requested:
        summary[split], frames[split] = evaluation.evaluate_split(
            resolved["model"],
            splits[split],
            image_size=resolved["image_size"],
            threshold=resolved["threshold"],
            device=resolved["device"],
            amp=amp,
            sam2_masks=sam2_path,
            limit=args.limit,
        )
    return summary, frames


def _output_dir(args: argparse.Namespace, cfg: training.TrainConfig) -> Path:
    """Resolve the evaluation output directory."""
    if args.out:
        return Path(args.out)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(cfg.checkpoint["dir"]) / cfg.crop_id / f"eval-{stamp}"


def _write_frames(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    """Write per-frame metrics as CSV."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(evaluation.PER_FRAME_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    column: "" if row.get(column) is None else row.get(column)
                    for column in evaluation.PER_FRAME_COLUMNS
                }
            )


def _print_table(summary: Mapping[str, Mapping[str, object]]) -> None:
    """Print the per-split metric table."""
    header = (
        f"{'split':<6}{'n':>5}{'Dice':>8}{'IoU':>8}{'Prec':>8}{'Rec':>8}"
        f"{'med|dA|%':>10}{'p90%':>8}{'ceil':>8}"
    )
    print(header)
    for split, stats in summary.items():
        print(
            f"{split:<6}{int(stats['n']):>5}{float(stats['dice']):>8.4f}"
            f"{float(stats['iou']):>8.4f}{float(stats['precision']):>8.4f}"
            f"{float(stats['recall']):>8.4f}"
            f"{float(stats['area_abs_pct_error_median']):>10.2f}"
            f"{float(stats['area_abs_pct_error_p90']):>8.2f}"
            f"{float(stats['label_ceiling_dice']):>8.4f}"
        )


def _register(
    args: argparse.Namespace,
    cfg: training.TrainConfig,
    resolved: Mapping[str, Any],
    summary: Mapping[str, Mapping[str, object]],
) -> None:
    """Write the registry entry for a promoted checkpoint."""
    checkpoint = Path(str(resolved["checkpoint"])).resolve()
    try:
        stored = checkpoint.relative_to(repo_root()).as_posix()
    except ValueError:
        stored = checkpoint.as_posix()
    config = resolved["config"]
    entry = {
        "crop_id": cfg.crop_id,
        "arch": config.arch,
        "encoder": config.encoder,
        "encoder_weights": config.encoder_weights,
        "decoder_channels": config.decoder_channels,
        "classes": config.classes,
        "checkpoint": stored,
        "sha256": sha256_file(checkpoint),
        "image_size": list(resolved["image_size"]),
        "threshold": float(resolved["threshold"]),
        "val_dice": float(resolved["best_val_dice"]),
        "test": dict(summary["test"]),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
    }
    write_registry_entry(
        Path(cfg.registry["path"]), cfg.model_id, entry, force=args.force_register
    )
    print(json.dumps(entry, indent=2, sort_keys=True))


def _git_sha() -> str:
    """Return the current git HEAD, or ``"unknown"``."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root(),
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
