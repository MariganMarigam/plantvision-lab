"""Idempotent original store: JPEG + JSON sidecar per accepted frame."""

import json
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> str:
    """Server-clock UTC timestamp (IP Webcam photo requests carry none)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sidecar_sha(sidecar: Path) -> str:
    """sha256 recorded in a sidecar, or "" if unreadable/malformed."""
    try:
        data = json.loads(sidecar.read_text())
    except (json.JSONDecodeError, OSError):
        return ""
    sha = data.get("sha256", "")
    return sha if isinstance(sha, str) else ""


def store_original(image_bytes: bytes, meta: dict, originals_dir: Path) -> tuple[Path, bool]:
    """Store one original JPEG + sidecar, idempotent by sha256.

    Directory layout: <originals_dir>/<camera_id>/<zone_slug>/<day>/<captured_at_compact>_<sha16>.jpg
    A frame is considered a duplicate when a stored sidecar anywhere under the
    same day directory already carries the same sha256 (same-path re-send or a
    re-capture of identical bytes) — then no file is rewritten.

    Args:
        image_bytes: Raw JPEG bytes to persist.
        meta: Metadata dict (sha256, captured_at, camera_id, zone_id, ...).
        originals_dir: Root directory for originals.

    Returns:
        (path, stored) where path is the original's .jpg path and stored=False
        means a duplicate already existed.

    Raises:
        OSError: On disk-full/permission failures — propagates to the caller,
            which spools the frame.
    """
    day = meta["captured_at"][:10]
    zone_slug = meta["zone_id"].replace("/", "_")
    directory = Path(originals_dir) / meta["camera_id"] / zone_slug / day
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{meta['captured_at'].replace(':', '').replace('-', '')}_{meta['sha256'][:16]}.jpg"
    path = directory / name
    sidecar = path.with_suffix(".json")

    if path.exists() and _sidecar_sha(sidecar) == meta["sha256"]:
        return path, False
    for candidate in sorted(directory.glob("*.json")):
        if _sidecar_sha(candidate) == meta["sha256"]:
            return candidate.with_suffix(".jpg"), False

    if path.exists():
        # Same compact timestamp but different content hash — keep both.
        path = directory / (path.stem + "_1.jpg")

    path.write_bytes(image_bytes)
    sidecar = path.with_suffix(".json")
    sidecar.write_text(json.dumps({**meta, "received_at": _utc_now()}, indent=2) + "\n")
    return path, True


def build_sha_index(originals_dir: str | Path) -> dict[str, Path]:
    """Map sha256 -> stored .jpg path for the WHOLE originals tree.

    The pull path's ``store_original`` only dedupes within one day directory,
    so a global check is required when the same bytes may already have been
    stored under a different ``captured_at`` day (e.g. a frame first pulled
    with a server-clock timestamp, then imported with its EXIF timestamp).

    Args:
        originals_dir: Root of the originals tree (may not exist yet).

    Returns:
        Dict mapping every sha256 found in the sidecars to its ``.jpg`` path
        (first writer wins; duplicate sha across days -> first path in
        ``rglob`` order, the value is informational only). Missing dir ->
        empty dict. Sidecars without their ``.jpg`` are still indexed (only
        keys are used) and malformed sidecars are skipped.
    """
    index: dict[str, Path] = {}
    root = Path(originals_dir)
    if not root.exists():
        return index
    for sidecar in root.rglob("*.json"):
        sha = _sidecar_sha(sidecar)
        if sha and sha not in index:
            index[sha] = sidecar.with_suffix(".jpg")
    return index
