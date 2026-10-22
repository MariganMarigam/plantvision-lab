"""Build manifest.csv from proposals + decisions logs (plan Step 9)."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Sequence

from plantvision.labeling.store import (
    build_manifest,
    latest_decisions,
    read_jsonl,
    write_manifest_csv,
)

SPLITS: tuple[str, ...] = ("train", "val", "test")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    p = argparse.ArgumentParser(
        description="Build the labeled-dataset manifest from JSONL logs."
    )
    p.add_argument("--labels", default="data/labels/v1")
    p.add_argument(
        "--split-strategy", choices=("temporal", "group"), default="temporal"
    )
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    args = parse_args(argv)
    labels = Path(args.labels)
    proposals = read_jsonl(labels / "proposals.jsonl")
    if not proposals:
        print("no proposals; run scripts/label_sam2.py first")
        return 2
    decisions = latest_decisions(read_jsonl(labels / "decisions.jsonl"))
    try:
        rows = build_manifest(proposals, decisions, args.split_strategy)
    except ValueError as exc:
        print(str(exc))
        return 2
    write_manifest_csv(rows, labels / "manifest.csv")

    n = len(rows)
    reviewed = sum(1 for r in rows if r["accepted"] in ("0", "1"))
    accepted = sum(1 for r in rows if r["accepted"] == "1")
    for split in SPLITS:
        count = sum(1 for r in rows if r["split"] == split)
        acc = sum(1 for r in rows if r["split"] == split and r["accepted"] == "1")
        print(f"{split}={count} (accepted={acc})")
    print(f"reviewed={reviewed}/{n} accepted={accepted}/{n}")

    group_splits: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        group_splits[str(row["group_key"])].add(str(row["split"]))
    for group, spans in sorted(group_splits.items()):
        if len(spans) > 1:
            print(f"WARNING: group {group} spans splits {sorted(spans)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
