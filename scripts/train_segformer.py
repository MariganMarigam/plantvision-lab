"""Train the SegFormer-b0 student (P2)."""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import plantvision.ml.train as training

RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]+")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Train the SegFormer-b0 student.")
    parser.add_argument("--config", default="configs/train.yaml")
    parser.add_argument("--dataset", default="", help="Override dataset root")
    parser.add_argument("--out", default="experiments", help="Run output root")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--num-workers", type=int, default=None)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default=None)
    parser.add_argument("--limit-train", type=int, default=0)
    parser.add_argument("--limit-val", type=int, default=0)
    parser.add_argument("--resume", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    args = parse_args(argv)
    dataset_root = Path(args.dataset) if args.dataset else None
    try:
        cfg = training.load_train_config(args.config)
        cfg = dataclasses.replace(
            cfg,
            **{
                key: value
                for key, value in (
                    ("device", args.device),
                    ("num_workers", args.num_workers),
                )
                if value is not None
            },
        )
        if args.dry_run:
            result = training.dry_run(
                cfg, dataset_root=dataset_root, batch_size=args.batch_size
            )
            print(json.dumps(result, indent=2))
            return 0
        run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if not run_id or not RUN_ID_PATTERN.fullmatch(run_id):
            print(f"invalid run id: {run_id!r}", file=sys.stderr)
            return 2
        summary = training.train(
            cfg,
            dataset_root=dataset_root,
            out_dir=Path(args.out),
            run_id=run_id,
            epochs=args.epochs,
            batch_size=args.batch_size,
            limit_train=args.limit_train,
            limit_val=args.limit_val,
            resume=Path(args.resume) if args.resume else None,
        )
        print(json.dumps(summary, indent=2))
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
