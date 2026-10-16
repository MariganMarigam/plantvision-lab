"""Incremental metrics runner (P1 data flywheel): update the time-series store.

Scans ``--originals`` for frames not yet in ``--store`` (idempotent by the
sidecar ``sha256``), measures them with the configured pipeline, appends one
row per new frame, and regenerates the per-zone projected-area plots from the
full store. Designed to run right after every capture; per-frame errors are
non-fatal and reported in the JSON summary.
"""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from plantvision.analytics.timeseries import run_update


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments (all with plan defaults)."""
    parser = argparse.ArgumentParser(
        description="Append newly captured frames to the metrics time-series store (P1)."
    )
    parser.add_argument("--originals", default="data/originals")
    parser.add_argument("--config", default="configs/pipeline.yaml")
    parser.add_argument("--store", default="data/derived/metrics/timeseries.csv")
    parser.add_argument("--out", default="data/derived/metrics")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the incremental update; 0 on success (even with per-frame errors).

    Args:
        argv: CLI arguments (defaults per :func:`parse_args` when None).

    Returns:
        0 on success; 1 only on a config error (missing/malformed config).
    """
    args = parse_args(argv)
    try:
        result = run_update(args.originals, args.config, args.store, args.out)
    except FileNotFoundError as exc:
        print(json.dumps({"status": "error", "error": f"config not found: {args.config} ({exc})"}))
        return 1
    except (ValueError, KeyError) as exc:
        print(json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"}))
        return 1
    print(
        json.dumps(
            {
                "status": "ok",
                "scanned": result.scanned,
                "measured": result.measured,
                "appended": result.appended,
                "skipped": result.skipped,
                "errors": result.errors,
                "rows_total": result.rows_total,
                "plots": [str(pp) for pp in result.plot_paths],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
