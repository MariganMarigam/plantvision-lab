"""Export accepted labels from manifest.csv (plan Step 10 CLI)."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Sequence

from plantvision.labeling.export import SPLITS, export_yolo_seg


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    p = argparse.ArgumentParser(
        description="Export accepted masks to YOLO-seg training files."
    )
    p.add_argument("--labels", default="data/labels/v1")
    p.add_argument("--originals", default="data/originals")
    p.add_argument("--out", default="data/labels/v1/export/yolo-seg")
    p.add_argument("--masks-out", default="data/labels/v1/export/png-masks")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    args = parse_args(argv)
    labels = Path(args.labels)
    manifest_path = labels / "manifest.csv"
    if not manifest_path.exists():
        print("manifest.csv not found; run scripts/build_label_manifest.py first")
        return 2
    with open(manifest_path, "r", encoding="utf-8", newline="\n") as fh:
        rows = list(csv.DictReader(fh))
    stats = export_yolo_seg(
        rows,
        Path(args.originals),
        labels,
        Path(args.out),
        Path(args.masks_out),
    )
    print(
        f"exported={stats['exported']} skipped_degenerate={stats['skipped_degenerate']} "
        f"accepted_missing={stats['accepted_missing']} -> {args.out}"
    )
    for split in SPLITS:
        if stats["per_split"][split]["accepted"] == 0:
            print(f"WARNING: split {split} has no accepted rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
