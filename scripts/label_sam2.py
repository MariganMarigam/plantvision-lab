"""Batch SAM2 label proposer CLI (plan Step 8).

For every sha-keyed frame under ``--originals``: compute the classical
ROI box prior, ask SAM2 for a mask, store mask + overlay + proposal
line. Idempotent by sha256: a frame is skipped when its mask PNG exists
AND a proposal line is already in the log, unless ``--force``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import cv2

from plantvision.labeling.frames import FrameRecord, load_frames
from plantvision.labeling.prompts import full_frame_box, roi_box
from plantvision.labeling.review import render_overlay
from plantvision.labeling.sam2_backend import Sam2Error, Sam2Segmenter
from plantvision.labeling.store import append_jsonl, latest_proposals, read_jsonl, write_mask


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    p = argparse.ArgumentParser(description="Propose SAM2 labels for frames.")
    p.add_argument("--originals", default="data/originals",
                   help="dataset root to scan (e.g. data/originals)")
    p.add_argument("--labels", default="data/labels/v1")
    p.add_argument("--checkpoint", default="checkpoints/sam2.1_hiera_small.pt")
    p.add_argument("--config", default="configs/sam2.1/sam2.1_hiera_s.yaml")
    p.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    p.add_argument("--expand", type=float, default=0.15)
    p.add_argument("--limit", type=int, default=0,
                   help="stop after N frames (0 = all)")
    p.add_argument("--only", default="",
                   help="single sha256 (or prefix) to label")
    p.add_argument("--force", action="store_true",
                   help="regenerate even when a proposal already exists")
    return p.parse_args(argv)


def _record(
    frame: FrameRecord,
    score: float,
    area_fraction: float,
    box: tuple[int, int, int, int],
    box_source: str,
    args: argparse.Namespace,
    device: str,
) -> dict:
    """Build one proposals.jsonl record for a finished frame.

    Includes ``captured_at`` and ``group_key`` from the frame record so
    ``build_label_manifest`` (which only reads the logs) can join and
    sort without re-hashing the dataset.
    """
    return {
        "sha256": frame.sha256,
        "frame_relpath": frame.relpath,
        "mask_relpath": f"masks/{frame.sha256}.png",
        "overlay_relpath": f"overlays/{frame.sha256}.jpg",
        "box": list(box),
        "box_source": box_source,
        "score": round(score, 4),
        "area_fraction": round(area_fraction, 6),
        "width": frame.width,
        "height": frame.height,
        "model": Path(args.checkpoint).stem,
        "config": args.config,
        "checkpoint": args.checkpoint,
        "device": device,
        "captured_at": frame.captured_at,
        "group_key": frame.group_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    args = parse_args(argv)
    originals = Path(args.originals)
    labels = Path(args.labels)
    masks_dir = labels / "masks"
    overlays_dir = labels / "overlays"
    masks_dir.mkdir(parents=True, exist_ok=True)
    overlays_dir.mkdir(parents=True, exist_ok=True)
    proposals_path = labels / "proposals.jsonl"

    frames, skipped_orphans = load_frames(originals)
    if not frames:
        print(f"no frames found under {originals}")
        return 2
    if args.only:
        frames = [f for f in frames if f.sha256.startswith(args.only)]
        if not frames:
            print(f"no frame matches {args.only}")
            return 2
    if args.limit:
        frames = frames[: max(0, args.limit)]

    existing = latest_proposals(read_jsonl(proposals_path))
    try:
        segmenter = Sam2Segmenter(
            Path(args.checkpoint), args.config, args.device
        )
    except FileNotFoundError as exc:
        print(f"{exc}\nsee plan Section 1.3 for the install steps")
        return 2
    except Sam2Error as exc:
        print(f"{exc}\nsee plan Section 1.3 for the install steps")
        return 2

    done = skipped = errors = 0
    for frame in frames:
        mask_path = masks_dir / f"{frame.sha256}.png"
        overlay_path = overlays_dir / f"{frame.sha256}.jpg"
        if not args.force and mask_path.exists() and frame.sha256 in existing:
            skipped += 1
            continue
        image = cv2.imread(str(frame.jpg))
        if image is None:
            errors += 1
            print(f"cannot read {frame.jpg}")
            continue
        box = roi_box(image, expand=args.expand)
        box_source = "hsv"
        if box is None:
            box = full_frame_box(image)
            box_source = "full_frame"
        try:
            proposal = segmenter.segment(image, box)
        except Exception as exc:  # noqa: BLE001 (per plan: count + continue)
            errors += 1
            print(f"ERROR {frame.sha256[:12]}: {exc}")
            continue
        write_mask(proposal.mask, mask_path)
        if not cv2.imwrite(str(overlay_path), render_overlay(image, proposal.mask)):
            raise RuntimeError(f"cannot write overlay: {overlay_path}")
        height, width = image.shape[:2]
        record = _record(
            frame,
            proposal.score,
            cv2.countNonZero(proposal.mask) / (height * width),
            box,
            box_source,
            args,
            segmenter.device,
        )
        append_jsonl(proposals_path, record)
        done += 1
    print(
        f"labelled={done} skipped={skipped} errors={errors} "
        f"orphans={skipped_orphans} -> {labels}"
    )
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
