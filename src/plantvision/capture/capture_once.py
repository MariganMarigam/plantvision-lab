"""One-shot capture: pull a frame, store it idempotently, log gaps.

Cadence is owned by the systemd timer (Task 2.7); this module self-gates on
the photoperiod light window (decision D8) and survives transient failures
via retry/backoff and the local spool.
"""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from plantvision.capture.metadata import build_metadata
from plantvision.capture.pull import CaptureError, fetch_photo
from plantvision.capture.queue import CaptureQueue
from plantvision.capture.store import store_original

_HHMM_RE = re.compile(r"\d{2}:\d{2}")

_FAILURE_STATUSES = {"error"}


def _utc_now() -> str:
    """UTC timestamp in the ISO-8601 Z format used for captured_at/received_at/ts."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _local_now(tz_name: str) -> datetime:
    """Wall-clock now in the configured timezone ("local" = system tz)."""
    if tz_name == "local":
        return datetime.now().astimezone()
    return datetime.now(ZoneInfo(tz_name))


def _parse_hhmm(value: str) -> int:
    """Parse HH:MM into minutes-since-midnight; ValueError on format mismatch."""
    if not _HHMM_RE.fullmatch(value):
        raise ValueError(f"invalid HH:MM time: {value!r}")
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def in_light_window(now_local: datetime, start: str, end: str) -> bool:
    """True when now_local falls inside the [start, end) light window.

    Args:
        now_local: Wall-clock time in the window's timezone.
        start: Window start "HH:MM" (inclusive).
        end: Window end "HH:MM" (exclusive). start == end means 24 h.

    Returns:
        True if inside the window (handles windows wrapping midnight).

    Raises:
        ValueError: If start/end are not "HH:MM" strings.
    """
    start_minutes = _parse_hhmm(start)
    end_minutes = _parse_hhmm(end)
    minutes = now_local.hour * 60 + now_local.minute
    if start_minutes == end_minutes:
        return True
    if start_minutes < end_minutes:
        return start_minutes <= minutes < end_minutes
    return minutes >= start_minutes or minutes < end_minutes


def _load_config(config_path: str | Path) -> dict:
    """Load the capture YAML config (missing file -> FileNotFoundError)."""
    return yaml.safe_load(Path(config_path).read_text())


def _log_jsonl(log_path: Path, record: dict[str, Any]) -> None:
    """Append one JSONL record to the capture log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record) + "\n")


def run_once(config_path: str | Path) -> dict:
    """Capture one frame according to config; returns a JSON-able status dict."""
    cfg = _load_config(config_path)
    log_path = Path(cfg["log_path"])
    window = cfg.get("light_window", {"start": "06:00", "end": "22:00", "tz": "local"})
    dark_policy = cfg.get("dark_policy", "skip")
    now_local = _local_now(window.get("tz", "local"))
    inside = in_light_window(now_local, window["start"], window["end"])

    if dark_policy == "skip" and not inside:
        _log_jsonl(log_path, {"ts": _utc_now(), "status": "skipped_dark"})
        return {"status": "skipped_dark"}

    # Device clock proxy: server UTC now until the phone-side push mode exists.
    captured_at = _utc_now()

    data: bytes | None = None
    last_error = ""
    backoffs = list(cfg.get("retry_backoff_seconds", [2, 5, 15, 60, 300]))
    retry_max = int(cfg["retry_max"])
    for attempt in range(retry_max + 1):
        try:
            data = fetch_photo(cfg["source_url"], timeout_s=float(cfg["timeout_seconds"]))
            break
        except CaptureError as exc:
            last_error = str(exc)
            if attempt < retry_max:
                time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
    if data is None:
        _log_jsonl(log_path, {"ts": _utc_now(), "status": "gap", "error": last_error})
        return {"status": "error", "error": last_error}

    meta = build_metadata(data, captured_at, cfg["camera_id"], cfg["zone_id"])
    meta["quality"] = "dark" if dark_policy == "tag" and not inside else "ok"

    try:
        path, stored = store_original(data, meta, Path(cfg["originals_dir"]))
    except OSError as exc:
        CaptureQueue(Path(cfg["spool_dir"])).add(data, meta)
        record = {"ts": _utc_now(), "status": "spooled", "sha256": meta["sha256"], "error": str(exc)}
        _log_jsonl(log_path, record)
        return {"status": "error", "error": "storage unavailable"}

    status = "ok" if stored else "duplicate"
    _log_jsonl(
        log_path,
        {"ts": _utc_now(), "status": status, "sha256": meta["sha256"], "path": str(path)},
    )
    return {"status": status, "sha256": meta["sha256"], "path": str(path)}


def drain_queue(config_path: str | Path) -> int:
    """Retry spooled frames; returns how many were newly stored."""
    cfg = _load_config(config_path)
    queue = CaptureQueue(Path(cfg["spool_dir"]))
    stored_count = 0
    for jpg_path, meta in queue.items():
        try:
            _, stored = store_original(jpg_path.read_bytes(), meta, Path(cfg["originals_dir"]))
        except OSError:
            continue
        queue.remove(meta["sha256"])
        if stored:
            stored_count += 1
    return stored_count


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: run_once + drain_queue, print JSON summary.

    Returns:
        0 on ok/duplicate/skipped_dark, 1 on error (config missing, invalid
        config values, transport failure, or unhandled exceptions, which are
        logged to the capture log when the config yields one).
    """
    parser = argparse.ArgumentParser(description="PlantVision one-shot capture")
    parser.add_argument("--config", default="configs/capture.yaml")
    args = parser.parse_args(argv)

    result: dict[str, Any] = {}
    drained = 0
    try:
        result = run_once(args.config)
        drained = drain_queue(args.config)
    except FileNotFoundError as exc:
        result = {"status": "error", "error": f"config not found: {args.config} ({exc})"}
    except (ValueError, ZoneInfoNotFoundError, KeyError) as exc:
        result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    summary = {**result, "drained": drained}
    print(json.dumps(summary))
    if result.get("status") == "error":
        _log_failure(args.config, result.get("error", "unknown error"))
        return 1
    return 0


def _log_failure(config_path: str, error: str) -> None:
    """Best-effort gap log for failures happening outside run_once's scope."""
    try:
        cfg = yaml.safe_load(Path(config_path).read_text())
        log_path = cfg.get("log_path")
        if log_path:
            _log_jsonl(Path(log_path), {"ts": _utc_now(), "status": "gap", "error": error})
    except (OSError, yaml.YAMLError):
        pass


if __name__ == "__main__":
    raise SystemExit(main())
