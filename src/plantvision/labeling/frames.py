"""Scan captured frames + sidecars into sha256-keyed records.

Reads ``data/originals/**/*.jpg`` with ``<stem>.json`` sidecars,
recomputes the file sha256 at scan time and pairs it with the sidecar
metadata (``captured_at``, ``camera_id``, ``zone_id``, ``width``,
``height``). Orphan JPEGs without a sidecar are skipped and counted.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_CHUNK_BYTES: int = 1024 * 1024


@dataclass(frozen=True)
class FrameRecord:
    """One scanable frame keyed by the sha256 of its JPEG bytes."""

    sha256: str
    jpg: Path
    relpath: str  # posix-style, relative to the originals root
    captured_at: str  # ISO8601 string copied from the sidecar
    width: int
    height: int
    group_key: str  # "<camera_id>/<zone_id>/<YYYY-MM-DD>"


def file_sha256(path: Path) -> str:
    """Compute the sha256 hex digest of a file's bytes.

    Args:
        path: File to hash; read in 1 MiB chunks.

    Returns:
        Lowercase 64-hex sha256 digest.

    Raises:
        OSError: If the file cannot be read (propagated).
    """
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def group_key_for(sidecar: dict[str, Any], captured_at: str) -> str:
    """Derive the ``(camera, zone, date)`` leakage group of a capture.

    Args:
        sidecar: Parsed sidecar JSON (uses ``camera_id`` and ``zone_id``,
            falling back to ``"unknown"``).
        captured_at: ISO8601 capture timestamp; the first 10 characters
            are used as the ``YYYY-MM-DD`` date part.

    Returns:
        ``"<camera_id>/<zone_id>/<YYYY-MM-DD>"`` with ``/`` in the zone id
        replaced by ``_`` so the key stays path-like.
    """
    date = captured_at[:10]
    zone = str(sidecar.get("zone_id", "unknown")).replace("/", "_")
    camera = str(sidecar.get("camera_id", "unknown"))
    return f"{camera}/{zone}/{date}"


def load_frames(originals: Path) -> tuple[list[FrameRecord], int]:
    """Load every JPEG that has a sidecar under ``originals``.

    Args:
        originals: Root directory (``data/originals``) to scan recursively.

    Returns:
        ``(records, skipped)`` where records are sorted by ``(captured_at,
        sha256)`` ascending and ``skipped`` counts orphan JPEGs (missing
        sidecar or missing/empty ``captured_at``).
    """
    frames: list[FrameRecord] = []
    skipped = 0
    for jpg in sorted(originals.rglob("*.jpg")):
        sidecar_path = jpg.with_suffix(".json")
        if not sidecar_path.exists():
            skipped += 1
            continue
        sidecar: dict[str, Any] = json.loads(
            sidecar_path.read_text(encoding="utf-8")
        )
        captured_at = str(sidecar.get("captured_at", ""))
        if not captured_at:
            skipped += 1
            continue
        sha = file_sha256(jpg)
        sidecar_sha = sidecar.get("sha256")
        if sidecar_sha is not None and str(sidecar_sha) != sha:
            warnings.warn(f"sidecar sha mismatch: {jpg}", UserWarning)
        frames.append(
            FrameRecord(
                sha256=sha,
                jpg=jpg,
                relpath=jpg.relative_to(originals).as_posix(),
                captured_at=captured_at,
                width=int(sidecar["width"]),
                height=int(sidecar["height"]),
                group_key=group_key_for(sidecar, captured_at),
            )
        )
    frames.sort(key=lambda r: (r.captured_at, r.sha256))
    return frames, skipped

