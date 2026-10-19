"""Download the ML model weights declared in configs/models.yaml.

Stdlib-only networking (``urllib.request``). Torch must NOT be imported here:
this tool also runs on hosts without the ML stack (it creates ``models/``).

Behaviour:
- downloads into ``<storage_dir>/<name>/<filename>`` (atomic ``.part`` rename);
- verifies the pinned ``sha256`` when present;
- otherwise records a TOFU hash sidecar ``<filename>.sha256``;
- is idempotent (skips when the file exists and the checksum matches);
- honors ``--dry-run``, ``--only NAME``, ``--record-hashes`` and exits non-zero
  on any failure, printing a one-line JSON summary.

Usage:
    python scripts/download_models.py [--dry-run] [--only NAME] [--record-hashes]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = ROOT / "configs" / "models.yaml"
CHUNK_BYTES = 1 << 20  # 1 MiB
REQUIRED_KEYS: tuple[str, ...] = ("name", "task", "license", "url", "filename")
OK_STATUSES = frozenset({"downloaded", "skipped", "tofu", "dry-run"})


@dataclass(frozen=True)
class ModelSpec:
    """One registry entry describing a downloadable model."""

    name: str
    task: str
    license: str
    url: str
    filename: str
    sha256: str | None
    size_mb: float
    notes: str = ""
    optional: bool = False


def load_registry(path: Path) -> tuple[str, list[ModelSpec]]:
    """Parse the YAML registry into a storage dir name and validated specs.

    Args:
        path: Registry YAML path.

    Returns:
        Tuple of ``(storage_dir, [ModelSpec, ...])``; ``storage_dir`` is
        repo-relative.

    Raises:
        ValueError: When an entry is missing a required key.
    """
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    storage_dir = str(raw.get("storage_dir", "models"))
    specs: list[ModelSpec] = []
    for idx, entry in enumerate(raw.get("models") or [], start=1):
        missing = [key for key in REQUIRED_KEYS if not entry.get(key)]
        if missing:
            label = entry.get("name", f"#{idx}")
            raise ValueError(f"registry entry {label!r}: missing key(s): {', '.join(missing)}")
        specs.append(
            ModelSpec(
                name=str(entry["name"]),
                task=str(entry["task"]),
                license=str(entry["license"]),
                url=str(entry["url"]),
                filename=str(entry["filename"]),
                sha256=None if entry.get("sha256") is None else str(entry["sha256"]),
                size_mb=float(entry.get("size_mb") or 0.0),
                notes=str(entry.get("notes", "")),
                optional=bool(entry.get("optional", False)),
            )
        )
    return storage_dir, specs


def file_sha256(path: Path, chunk: int = CHUNK_BYTES) -> str:
    """Compute the sha256 hex digest of a file (streamed, fixed chunk size)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def fetch(url: str, dest: Path) -> int:
    """Stream ``url`` into ``dest`` via stdlib urllib (atomic part-rename).

    Args:
        url: Direct download URL (http/https/file are all supported).
        dest: Final destination path; written via ``<dest>.part`` then renamed.

    Returns:
        Number of bytes downloaded.

    Raises:
        urllib.error.URLError / OSError: Propagated on network failure.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    total = 0
    with urllib.request.urlopen(url, timeout=60) as resp, tmp.open("wb") as out:
        while True:
            block = resp.read(CHUNK_BYTES)
            if not block:
                break
            out.write(block)
            total += len(block)
    tmp.rename(dest)
    return total


def dest_for(spec: ModelSpec, storage_root: Path) -> Path:
    """Destination path for a spec: ``<storage_root>/<name>/<filename>``."""
    return storage_root / spec.name / spec.filename


def run_one(spec: ModelSpec, storage_root: Path, dry_run: bool) -> dict[str, Any]:
    """Download (or skip) one model; never raises — failures become status entries.

    Args:
        spec: The model spec to process.
        storage_root: Resolved storage root directory.
        dry_run: When True, report the plan without touching the disk.

    Returns:
        Result dict with ``name``, ``status`` (``downloaded``/``skipped``/
        ``tofu``/``failed``/``dry-run``) and details (``error``/``sha256``).
    """
    dest = dest_for(spec, storage_root)
    result: dict[str, Any] = {"name": spec.name, "dest": str(dest)}
    if dry_run:
        result["status"] = "dry-run"
        return result
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (spec.sha256 is None or file_sha256(dest) == spec.sha256):
        result["status"] = "skipped"
        result["reason"] = "checksum-matches" if spec.sha256 else "trusted-on-first-use"
        return result
    try:
        fetch(spec.url, dest)
    except (urllib.error.URLError, OSError) as exc:
        dest.with_name(dest.name + ".part").unlink(missing_ok=True)
        result["status"] = "failed"
        result["error"] = f"download failed: {exc}"
        return result
    computed = file_sha256(dest)
    if spec.sha256 is not None and computed != spec.sha256:
        dest.unlink(missing_ok=True)
        result["status"] = "failed"
        result["error"] = f"checksum mismatch for {dest}: got {computed}, expected {spec.sha256}"
        return result
    if spec.sha256 is None:
        sidecar = dest.with_name(dest.name + ".sha256")
        sidecar.write_text(f"{computed}  {spec.filename}\n", encoding="utf-8")
        result["status"] = "tofu"
        print(
            f"note: no sha256 pinned for {spec.name}; TOFU hash recorded in {sidecar.name}",
            file=sys.stderr,
        )
    else:
        result["status"] = "downloaded"
    result["sha256"] = computed
    return result


def record_hashes(registry_path: Path, results: list[dict[str, Any]]) -> None:
    """Write computed hashes back into the registry (``sha256: null`` -> value).

    Args:
        registry_path: Registry YAML to update in place.
        results: Result dicts from ``run_one`` carrying ``name`` + ``sha256``.
    """
    computed = {
        r["name"]: r["sha256"] for r in results if r.get("sha256") and r["status"] in OK_STATUSES
    }
    if not computed:
        return
    lines = registry_path.read_text(encoding="utf-8").splitlines(keepends=True)
    current: str | None = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("- name:"):
            current = stripped.removeprefix("- name:").strip()
        elif current in computed and stripped.startswith("sha256:"):
            lines[idx] = re.sub(
                r"sha256:\s*null.*", f"sha256: {computed[current]}", line, count=1
            )
    registry_path.write_text("".join(lines), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the downloader CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY,
                        help="Registry YAML path (default: configs/models.yaml).")
    parser.add_argument("--storage-dir", type=Path, default=None,
                        help="Override the registry storage_dir (default: repo-relative 'models').")
    parser.add_argument("--only", action="append", default=[], metavar="NAME",
                        help="Process only this model (repeatable).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the plan without writing anything.")
    parser.add_argument("--record-hashes", action="store_true",
                        help="Write computed hashes back into the registry (null -> value).")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the downloader; exit 0 when every selected model is OK, else 1."""
    args = parse_args(argv)
    storage_name, specs = load_registry(args.registry)
    only = set(args.only)
    if only - {s.name for s in specs}:
        print(f"error: unknown model(s): {', '.join(sorted(only))}", file=sys.stderr)
        return 1
    if args.storage_dir is not None:
        root = Path(args.storage_dir)
    else:
        declared = Path(storage_name)
        root = declared if declared.is_absolute() else ROOT / declared
    results: list[dict[str, Any]] = []
    for spec in specs:
        if only and spec.name not in only:
            continue
        if spec.optional and not only:
            results.append({
                "name": spec.name, "dest": str(dest_for(spec, root)),
                "status": "skipped", "reason": "optional",
            })
            continue
        results.append(run_one(spec, root, args.dry_run))
    if args.record_hashes and not args.dry_run:
        record_hashes(args.registry, results)
    summary = {
        "ok": all(r["status"] in OK_STATUSES for r in results),
        "storage_dir": str(root),
        "results": results,
    }
    print(json.dumps(summary))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
