"""Build the static growth dashboard from one or more metrics CSVs.

The default basil dataset is the SAM2 bridge (mask-derived), not the legacy
white-light classical series. Prints exactly one JSON line:
``{"status": "ok", ...}`` on success or ``{"status": "error", ...}`` on a
data/IO failure (exit 1); argparse usage errors exit 2.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from plantvision.analytics.dashboard import Dataset, write_dashboard

_DEFAULT_DATASETS = (
    Dataset(
        "basil farm-02 · SAM2",
        Path("data/derived/metrics/basil-farm02-sam2.csv"),
        "SAM2 mask-derived series (sam2.1_hiera_small, marker prompt), not a "
        "classical HSV/ExG measurement; review status stays in the label "
        "manifest; scale recomputed per frame from the 45 mm ArUco tag.",
    ),
    Dataset("lettuce", Path("data/derived/metrics/lettuce-timeseries.csv")),
)


def _dataset_spec(value: str) -> Dataset:
    """Parse a ``LABEL=PATH`` dataset argument."""
    if "=" not in value:
        raise argparse.ArgumentTypeError("--dataset must be LABEL=PATH")
    label, path = value.split("=", 1)
    if not label or not path:
        raise argparse.ArgumentTypeError("--dataset must be LABEL=PATH")
    return Dataset(label, Path(path))


def _parse_now(value: str) -> datetime:
    """Parse an ISO-8601 ``--now`` value; naive input is treated as UTC."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--now must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments (defaults cover the two known stores)."""
    parser = argparse.ArgumentParser(
        description="Render a self-contained static growth dashboard from metrics CSVs."
    )
    parser.add_argument(
        "--dataset", action="append", type=_dataset_spec, default=None,
        metavar="LABEL=PATH",
        help="dataset to render; repeatable (default: basil + lettuce stores)",
    )
    parser.add_argument(
        "--out", default="output/dashboard/index.html",
        help="destination HTML path",
    )
    parser.add_argument(
        "--pipeline-version", default="unrecorded",
        help="pipeline label shown on the cm² chart",
    )
    parser.add_argument(
        "--title", default="PlantVision · growth dashboard",
        help="page title",
    )
    parser.add_argument(
        "--now", type=_parse_now, default=None,
        help="ISO-8601 reference time for age/gap rules",
    )
    args = parser.parse_args(argv)
    if args.dataset is None:
        args.dataset = list(_DEFAULT_DATASETS)
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Run the dashboard builder; return the process exit code."""
    args = parse_args(argv)
    now = args.now or datetime.now(timezone.utc)
    try:
        result = write_dashboard(
            args.dataset,
            Path(args.out),
            now=now,
            pipeline_version=args.pipeline_version,
            title=args.title,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(json.dumps({
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }))
        return 1

    critical = sum(
        1 for finding in result.findings if finding.severity == "critical"
    )
    warn = sum(1 for finding in result.findings if finding.severity == "warn")
    print(json.dumps({
        "status": "ok",
        "out": str(result.out_path),
        "datasets": result.datasets,
        "rows": result.rows_total,
        "alerts": {"critical": critical, "warn": warn},
        "charts": result.charts,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
