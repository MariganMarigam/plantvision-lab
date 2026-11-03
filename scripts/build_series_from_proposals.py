"""Build the canonical basil series from SAM2 proposals + masks.

Prints exactly one JSON line: ``{"status": "ok", ...}`` on success or
``{"status": "error", ...}`` on a data/IO failure (exit 1); argparse usage
errors exit 2.
"""

from __future__ import annotations

import argparse
import json
import statistics
from typing import Sequence

from plantvision.analytics.proposal_series import (
    SeriesBuildResult,
    build_rows,
    read_proposals,
    read_review_status,
)
from plantvision.analytics.timeseries import replace_rows
from plantvision.vision.metrics import load_pipeline_config


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments (defaults cover the farm-02 SAM2 export)."""
    parser = argparse.ArgumentParser(
        description="Build canonical timeseries rows from SAM2 proposals + masks."
    )
    parser.add_argument(
        "--proposals", default="data/labels/farm02-v1/proposals.jsonl",
        help="proposal JSONL exported by label_sam2.py",
    )
    parser.add_argument(
        "--manifest", default="data/labels/farm02-v1/manifest.csv",
        help="review manifest (sha256,accepted)",
    )
    parser.add_argument(
        "--originals", default="data/originals/farm-02",
        help="root of the originals tree",
    )
    parser.add_argument(
        "--labels", default="data/labels/farm02-v1",
        help="root of the label export (mask_relpath base)",
    )
    parser.add_argument(
        "--config", default="configs/pipeline.yaml",
        help="pipeline config with the ArUco scale reference",
    )
    parser.add_argument(
        "--out", default="data/derived/metrics/basil-farm02-sam2.csv",
        help="destination timeseries CSV (rewritten atomically)",
    )
    parser.add_argument(
        "--review-status", choices=("all", "accepted"), default="all",
        help="include pending proposals (all) or only accepted (accepted)",
    )
    parser.add_argument(
        "--quality-mode", choices=("physical", "none"), default="physical",
        help=(
            "physical: recompute blur/dark/bright from the sidecar raw metrics; "
            "none: leave quality_flag blank"
        ),
    )
    parser.add_argument(
        "--biosource", default="basil", help="biosource_id written to every row"
    )
    parser.add_argument(
        "--experiment-id", default="farm02-sam2-v1",
        help="experiment_id written to every row",
    )
    parser.add_argument(
        "--observation-unit", default="farm-02/farm_zone-b",
        help="observation_unit_id written to every row",
    )
    return parser.parse_args(argv)


def _summary(result: SeriesBuildResult, out: str) -> dict:
    """Build the single-line JSON summary for a successful build."""
    rows = result.rows
    scale_pct = round(100.0 * result.scale_rows / len(rows), 2)
    median_area_px = statistics.median(float(row["area_px"]) for row in rows)
    cm2_values = [float(row["area_cm2"]) for row in rows if row["area_cm2"]]
    median_area_cm2 = statistics.median(cm2_values) if cm2_values else None
    return {
        "status": "ok",
        "out": out,
        "proposals": result.proposals,
        "rows": len(rows),
        "excluded_rejected": result.excluded_rejected,
        "excluded_review": result.excluded_review,
        "missing_review": result.missing_review,
        "missing_frame": result.missing_frame,
        "missing_mask": result.missing_mask,
        "missing_sidecar": result.missing_sidecar,
        "read_error": result.read_error,
        "scale_rows": result.scale_rows,
        "scale_pct": scale_pct,
        "trait_rows": result.trait_rows,
        "errors": len(result.errors),
        "first_at": rows[0]["captured_at"],
        "last_at": rows[-1]["captured_at"],
        "median_area_px": median_area_px,
        "median_area_cm2": median_area_cm2,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the series builder; return the process exit code."""
    args = parse_args(argv)
    try:
        cfg = load_pipeline_config(args.config)
        proposals = read_proposals(args.proposals)
        review = read_review_status(args.manifest)
        result = build_rows(
            proposals,
            review,
            originals_root=args.originals,
            labels_root=args.labels,
            review_status=args.review_status,
            quality_mode=args.quality_mode,
            marker_size_mm=cfg.scale.marker_size_mm,
            aruco_dict=cfg.scale.aruco_dict,
            biosource_id=args.biosource,
            experiment_id=args.experiment_id,
            observation_unit_id=args.observation_unit,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }))
        return 1

    if not result.rows:
        print(json.dumps({
            "status": "error",
            "error": "no rows selected",
            "excluded_rejected": result.excluded_rejected,
            "excluded_review": result.excluded_review,
        }))
        return 1

    replace_rows(args.out, result.rows)
    print(json.dumps(_summary(result, args.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
