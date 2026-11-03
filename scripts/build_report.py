"""Build the static PLANT_LAB dashboard v2 (self-contained HTML).

Prints exactly one JSON line: ``{"status": "ok", ...}`` on success. Data/IO
failures exit 1, argparse usage errors exit 2 and a page above the byte budget
exits 3.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import yaml

from plantvision.analytics.dashboard.build import build_report, load_panels
from plantvision.analytics.dashboard.model import build_payload

_DEFAULT_TITLE = "PLANT_LAB · growth dashboard"


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
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Render the self-contained PLANT_LAB dashboard v2."
    )
    parser.add_argument(
        "--panels", default="configs/dashboard-panels.yaml",
        help="panel config YAML",
    )
    parser.add_argument(
        "--out", default="output/dashboard/index.html",
        help="destination HTML path",
    )
    parser.add_argument(
        "--now", type=_parse_now, default=None,
        help="ISO-8601 reference time (default: last capture in the data)",
    )
    parser.add_argument(
        "--title", default=None, help="page title (default: config title)",
    )
    parser.add_argument(
        "--thumb-width", type=int, default=288, help="thumbnail width in px",
    )
    parser.add_argument(
        "--thumb-quality", type=int, default=58, help="JPEG quality 1-100",
    )
    parser.add_argument(
        "--no-frames", action="store_true", help="skip embedded thumbnails",
    )
    parser.add_argument(
        "--max-bytes", type=int, default=1_048_576,
        help="hard page-size budget in bytes",
    )
    parser.add_argument(
        "--dump-payload", default=None,
        help="write the JSON payload (without frames/cards) to this path",
    )
    parser.add_argument(
        "--lang", choices=("en", "ru"), default="en",
        help="initial page language",
    )
    return parser.parse_args(argv)


def _config_title(path: Path) -> str:
    """Read the title from the panel config, falling back to the default."""
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return _DEFAULT_TITLE
    if isinstance(data, dict) and str(data.get("title") or "").strip():
        return str(data["title"])
    return _DEFAULT_TITLE


def main(argv: Sequence[str] | None = None) -> int:
    """Run the builder; return the process exit code."""
    args = parse_args(argv)
    title = args.title or _config_title(Path(args.panels))
    try:
        panels = load_panels(Path(args.panels))
        if args.dump_payload:
            payload = build_payload(panels, now=args.now, title=title)
            Path(args.dump_payload).write_text(
                json.dumps(payload, sort_keys=True, ensure_ascii=False),
                encoding="utf-8",
            )
        result = build_report(
            panels,
            Path(args.out),
            now=args.now,
            title=title,
            thumb_width=args.thumb_width,
            thumb_quality=args.thumb_quality,
            include_frames=not args.no_frames,
            max_bytes=args.max_bytes,
            lang=args.lang,
        )
    except ValueError as exc:
        message = str(exc)
        if message.startswith("output ") and "exceeds budget" in message:
            size = message.split()[1]
            print(json.dumps({
                "status": "error",
                "error": f"budget: {message}",
                "bytes": int(size),
            }, sort_keys=True))
            return 3
        print(json.dumps({
            "status": "error",
            "error": f"{type(exc).__name__}: {message}",
        }, sort_keys=True))
        return 1
    except (FileNotFoundError, OSError, yaml.YAMLError) as exc:
        print(json.dumps({
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }, sort_keys=True))
        return 1

    critical = sum(1 for finding in result.findings if finding.severity == "critical")
    warn = sum(1 for finding in result.findings if finding.severity == "warn")
    print(json.dumps({
        "status": "ok",
        "out": str(result.out_path),
        "panels": result.panels,
        "rows": result.rows_total,
        "days": result.days,
        "alerts": {"critical": critical, "warn": warn},
        "charts": result.charts,
        "frames": result.frames,
        "bytes": result.bytes_total,
        "json_bytes": result.json_bytes,
        "now_source": result.now_source,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
