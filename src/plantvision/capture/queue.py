"""Local spool: frames held when storage is unavailable, drained later.

Module note: named `queue` per plan manifest; it does not shadow the stdlib
module of the same name (absolute imports resolve stdlib `queue` normally).
"""

import json
from pathlib import Path


class CaptureQueue:
    """File-based spool of undrained frames keyed by sha256."""

    def __init__(self, spool_dir: Path) -> None:
        """Create the spool directory if missing.

        Args:
            spool_dir: Directory holding <sha256>.jpg / <sha256>.json pairs.
        """
        self._dir = Path(spool_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def add(self, image_bytes: bytes, meta: dict) -> Path:
        """Spool one frame; returns its .jpg path inside the spool."""
        jpg_path = self._dir / f"{meta['sha256']}.jpg"
        jpg_path.write_bytes(image_bytes)
        (self._dir / f"{meta['sha256']}.json").write_text(json.dumps(meta, indent=2) + "\n")
        return jpg_path

    def items(self) -> list[tuple[Path, dict]]:
        """All spooled frames as (jpg_path, meta), oldest filename first.

        Malformed sidecars and orphan sidecars without a .jpg are skipped.
        """
        pairs: list[tuple[Path, dict]] = []
        for meta_file in sorted(self._dir.glob("*.json")):
            try:
                meta = json.loads(meta_file.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            jpg_path = meta_file.with_suffix(".jpg")
            if not jpg_path.exists():
                continue
            pairs.append((jpg_path, meta))
        return pairs

    def remove(self, sha256: str) -> None:
        """Delete both files of a spooled frame; missing files are fine."""
        for suffix in (".jpg", ".json"):
            path = self._dir / f"{sha256}{suffix}"
            if path.exists():
                path.unlink()

    def __len__(self) -> int:
        """Number of spooled sidecars (including malformed ones)."""
        return len(list(self._dir.glob("*.json")))
