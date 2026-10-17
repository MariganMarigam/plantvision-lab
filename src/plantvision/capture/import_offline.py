"""Offline import: ingest an external phone-frame folder into data/originals.

Store-and-forward ingest (P1): a phone stores frames locally while the PC is
off; the folder is copied over USB later and imported here. Frames land in the
SAME originals tree as the pull path, idempotently by global sha256, with
``captured_at`` = device time (exif -> filename -> mtime) and ``received_at`` =
import time. Every examined file produces exactly one JSONL decision record in
``data/capture.log`` (or one in-memory decision under ``--dry-run``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfoNotFoundError

import cv2
import numpy as np
import yaml

from plantvision.capture.capture_once import in_light_window
from plantvision.capture.metadata import build_metadata
from plantvision.capture.store import build_sha_index, store_original
from plantvision.capture.timestamps import format_utc, resolve_captured_at, resolve_tz
from plantvision.vision.quality import blur_score, brightness_score, quality_flags, red_dominance

_DEFAULT_IMPORT: dict[str, Any] = {
    "extensions": [".jpg", ".jpeg"],
    "brightness_min": 40.0,
    "brightness_max": 220.0,
    "blur_lapvar_min": 10.0,
    "red_dominance_min": 1.5,
    "archive_subdir": "_imported",
}

STATUSES: tuple[str, ...] = (
    "ok", "duplicate", "skipped_dark", "skipped_corrupt",
    "skipped_unsupported", "skipped_notime", "error",
)


@dataclass(frozen=True)
class FileDecision:
    """Outcome of examining one source file (one JSONL record when logged)."""

    source: str
    status: str
    reason: str = ""
    sha256: str = ""
    captured_at: str = ""
    time_source: str = ""
    path: str = ""
    duplicate_of: str = ""
    message: str = ""
    moved: bool = False
    brightness: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Flat dict with the full decision key set in a fixed order."""
        return {
            "source": self.source,
            "status": self.status,
            "reason": self.reason,
            "sha256": self.sha256,
            "captured_at": self.captured_at,
            "time_source": self.time_source,
            "path": self.path,
            "duplicate_of": self.duplicate_of,
            "message": self.message,
            "moved": self.moved,
            "brightness": self.brightness,
        }


@dataclass(frozen=True)
class ImportResult:
    """Run-level counts plus the per-file decisions (captured under dry-run)."""

    scanned: int
    imported: int
    duplicates: int
    skipped_dark: int
    skipped_corrupt: int
    skipped_unsupported: int
    skipped_notime: int
    errors: int
    moved: int
    dry_run: bool
    decisions: tuple[FileDecision, ...]


def _utc_now() -> str:
    """Import-clock UTC timestamp (same format as capture_once._utc_now)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _load_config(config_path: str | Path) -> dict:
    """Load the capture YAML config (missing file -> FileNotFoundError)."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _log_jsonl(log_path: Path, record: dict[str, Any]) -> None:
    """Append one JSONL record to the capture log (4-line primitive, kept local)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record) + "\n")


def _iter_source_files(root: Path, archive_subdir: str) -> list[Path]:
    """Sorted recursive file list under ``root``, skipping the archive subdir."""
    files: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if archive_subdir in rel.parts:
            continue
        files.append(p)
    return sorted(files, key=lambda q: str(q).lower())


def _decode_bgr(data: bytes) -> np.ndarray | None:
    """Decode JPEG bytes to BGR (OpenCV IMREAD_COLOR); None when undecodable."""
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    return arr


def _quality_meta(bgr: np.ndarray, thresholds: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """Measure brightness / blur / red dominance; adds informational flags.

    This is the only place a frame is measured: 4 pixel passes, and it does
    NOT touch the measurement module. The ``blur``/``dark``/``bright``/``red``
    flags are informational only and never cause a skip.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    brightness = brightness_score(gray)
    lapvar = blur_score(gray)
    red = red_dominance(bgr)
    flags = quality_flags(
        gray,
        blur_lapvar_min=float(thresholds["blur_lapvar_min"]),
        brightness_min=float(thresholds["brightness_min"]),
        brightness_max=float(thresholds["brightness_max"]),
    )
    if red >= float(thresholds["red_dominance_min"]):
        flags.append("red")
    extra = {
        "quality": "|".join(flags) if flags else "ok",
        "quality_flags": flags,
        "brightness": round(brightness, 2),
        "blur_lapvar": round(lapvar, 2),
        "red_dominance": round(red, 3),
    }
    return (extra, brightness)


def _process_one(path: Path, source: Path, cfg: dict, thresholds: dict[str, Any],
                 extensions: set[str], originals: Path, index: dict[str, Path],
                 run_seen: dict[str, str], tz: Any, window: dict, dry_run: bool,
                 move: bool) -> FileDecision:
    """Run the normative decision pipeline for one file (extension first)."""
    name = path.name
    if name.startswith("."):
        return FileDecision(str(path), "skipped_unsupported", reason="hidden")
    if path.suffix.lower() not in extensions:
        return FileDecision(str(path), "skipped_unsupported", reason="extension")
    try:
        data = path.read_bytes()
    except OSError as exc:
        return FileDecision(str(path), "error", reason="read", message=str(exc))
    sha = hashlib.sha256(data).hexdigest()
    if sha in index:
        return FileDecision(str(path), "duplicate", reason="stored", sha256=sha,
                            duplicate_of=str(index[sha]))
    if sha in run_seen:
        return FileDecision(str(path), "duplicate", reason="within_run", sha256=sha,
                            duplicate_of=run_seen[sha])
    guess = resolve_captured_at(data, path, tz)
    if guess is None:
        return FileDecision(str(path), "skipped_notime", reason="time", sha256=sha)
    captured_at = format_utc(guess.utc)
    local = guess.utc.astimezone(tz)
    if not in_light_window(local, window["start"], window["end"]):
        return FileDecision(str(path), "skipped_dark", reason="window", sha256=sha,
                            captured_at=captured_at, time_source=guess.source)
    try:
        meta = build_metadata(data, captured_at, cfg["camera_id"], cfg["zone_id"])
    except ValueError as exc:
        return FileDecision(str(path), "skipped_corrupt", reason="undecodable", sha256=sha,
                            message=str(exc))
    bgr = _decode_bgr(data)
    if bgr is None:
        return FileDecision(str(path), "skipped_corrupt", reason="undecodable", sha256=sha)
    extra, brightness = _quality_meta(bgr, thresholds)
    if brightness < float(thresholds["brightness_min"]):
        return FileDecision(str(path), "skipped_dark", reason="brightness", sha256=sha,
                            captured_at=captured_at, time_source=guess.source,
                            brightness=round(brightness, 2))
    meta.update(extra)
    meta["time_source"] = guess.source
    meta["source_relpath"] = str(path.relative_to(source))
    if dry_run:
        return FileDecision(str(path), "ok", reason="would_import", sha256=sha,
                            captured_at=captured_at, time_source=guess.source,
                            brightness=round(brightness, 2))
    try:
        stored_path, stored = store_original(data, meta, originals)
    except OSError as exc:
        # NO spooling: the source folder is the durable copy.
        return FileDecision(str(path), "error", reason="storage", sha256=sha,
                            captured_at=captured_at, time_source=guess.source,
                            message=str(exc))
    status = "ok" if stored else "duplicate"
    reason = "" if stored else "store_race"
    moved = False  # --move archive hook arrives in Step 7 (_archive_source)
    return FileDecision(str(path), status, reason=reason, sha256=sha, captured_at=captured_at,
                        time_source=guess.source, path=str(stored_path),
                        brightness=round(brightness, 2), moved=moved)


def _summarize(decisions: list[FileDecision], *, dry_run: bool) -> ImportResult:
    """Count decisions by status into an ImportResult."""
    counts = {s: 0 for s in STATUSES}
    for d in decisions:
        counts[d.status] += 1
    return ImportResult(
        scanned=len(decisions),
        imported=counts["ok"],
        duplicates=counts["duplicate"],
        skipped_dark=counts["skipped_dark"],
        skipped_corrupt=counts["skipped_corrupt"],
        skipped_unsupported=counts["skipped_unsupported"],
        skipped_notime=counts["skipped_notime"],
        errors=counts["error"],
        moved=sum(1 for d in decisions if d.moved),
        dry_run=dry_run,
        decisions=tuple(decisions),
    )


def _log_record(decision: FileDecision) -> dict[str, Any]:
    """One JSONL record for a decision; empty/None/False values are omitted."""
    record: dict[str, Any] = {"ts": _utc_now()}
    for k, v in decision.to_dict().items():
        if v not in ("", None, False):
            record[k] = v
    return record


def import_folder(source_dir: str | Path, config_path: str | Path, *,
                  dry_run: bool = False, move: bool = False) -> ImportResult:
    """Import every candidate frame from ``source_dir`` (dry-run-safe, idempotent).

    Args:
        source_dir: Folder copied from the phone; scanned recursively.
        config_path: Capture config path (originals/log/light_window/import).
        dry_run: Report decisions only; no writes at all.
        move: Reserved for the Step 7 archive hook (inert in copy mode).

    Returns:
        An :class:`ImportResult` with per-status counts and decisions.

    Raises:
        FileNotFoundError: Missing config or missing source directory.
        ValueError/KeyError/ZoneInfoNotFoundError/yaml.YAMLError: Bad config,
            propagated to the CLI.
    """
    cfg = _load_config(config_path)
    originals = Path(cfg["originals_dir"])
    log_path = Path(cfg["log_path"])
    window = cfg.get("light_window", {"start": "06:00", "end": "22:00", "tz": "local"})
    tz = resolve_tz(window.get("tz", "local"))
    thresholds = {**_DEFAULT_IMPORT, **cfg.get("import", {})}
    extensions = {str(e).lower() for e in thresholds["extensions"]}
    archive_subdir = str(thresholds["archive_subdir"])
    source = Path(source_dir)
    if not source.is_dir():
        raise FileNotFoundError(f"source directory not found: {source_dir}")
    index = build_sha_index(originals)
    run_seen: dict[str, str] = {}
    decisions: list[FileDecision] = []
    for path in _iter_source_files(source, archive_subdir):
        d = _process_one(path, source, cfg, thresholds, extensions, originals, index,
                         run_seen, tz, window, dry_run, move)
        decisions.append(d)
        if d.status in ("ok", "duplicate") and d.sha256:
            run_seen.setdefault(d.sha256, str(path))
        if not dry_run:
            _log_jsonl(log_path, _log_record(d))
    result = _summarize(decisions, dry_run=dry_run)
    if not dry_run:
        _log_jsonl(log_path, {
            "ts": _utc_now(), "status": "import_summary", "source": str(source),
            "scanned": result.scanned, "imported": result.imported,
            "duplicates": result.duplicates, "skipped_dark": result.skipped_dark,
            "skipped_corrupt": result.skipped_corrupt,
            "skipped_unsupported": result.skipped_unsupported,
            "skipped_notime": result.skipped_notime, "errors": result.errors,
            "moved": result.moved, "dry_run": False,
        })
    return result
