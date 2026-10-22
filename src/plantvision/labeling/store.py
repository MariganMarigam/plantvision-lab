"""Mask I/O, append-only JSONL logs, manifest build and deterministic splits.

Label store contract (plan Section 4):
- masks are ``(H, W)`` uint8 with values ``{0, 255}``, keyed by the full
  64-hex sha256 of the frame JPEG bytes;
- ``proposals.jsonl`` / ``decisions.jsonl`` are append-only; the LAST line
  for a sha256 wins;
- the manifest is regenerated deterministically; input order is
  irrelevant, no RNG.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np

LABEL_FOREGROUND: int = 255
"""Foreground value of every stored mask (OpenCV convention)."""

MANIFEST_COLUMNS: tuple[str, ...] = (
    "sha256",
    "frame_relpath",
    "mask_relpath",
    "accepted",
    "reject_reason",
    "reviewer",
    "reviewed_at",
    "split",
    "group_key",
    "captured_at",
    "confidence",
    "area_fraction",
    "box",
    "box_source",
    "model",
    "checkpoint",
    "created_at",
)
"""Exact column order of manifest.csv."""


def normalize_mask(mask: np.ndarray) -> np.ndarray:
    """Coerce an arbitrary mask-like array to ``(H, W)`` uint8 ``{0, 255}``.

    Args:
        mask: Array in one of: ``(H, W)`` numeric; ``(H, W)`` bool;
            ``(H, W, K)`` (channel 0 is used); float in ``[0, 1]``.

    Returns:
        Binary ``(H, W)`` uint8 array with values ``{0, 255}``.

    Raises:
        ValueError: If the input cannot be reduced to a 2-D mask.
    """
    arr = np.asarray(mask)
    if arr.ndim == 3:
        arr = arr[:, :, 0]
        if arr.ndim == 3:
            raise ValueError(f"mask must reduce to 2-D, got shape={np.asarray(mask).shape}")
    if arr.dtype == bool:
        arr = arr.astype(np.uint8) * 255
    elif arr.max() <= 1:
        arr = arr * 255
    if arr.ndim != 2:
        raise ValueError(f"mask must be 2-D (H,W), got shape={arr.shape}")
    return np.where(arr > 0, 255, 0).astype(np.uint8)


def write_mask(mask: np.ndarray, path: Path) -> Path:
    """Normalize and write a binary mask PNG; parents are created.

    Args:
        mask: Any mask-like array accepted by :func:`normalize_mask`.
        path: Destination ``.png`` path.

    Returns:
        The destination path.

    Raises:
        RuntimeError: If OpenCV cannot write the file (e.g. bad path).
    """
    arr = normalize_mask(mask)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), arr):
        raise RuntimeError(f"cannot write mask: {path}")
    return path


def read_mask(path: Path) -> np.ndarray:
    """Read a stored mask PNG and verify it is binary.

    Args:
        path: Mask file readable by OpenCV.

    Returns:
        ``(H, W)`` uint8 array with values ``{0, 255}``.

    Raises:
        RuntimeError: If the file does not exist or cannot be read.
        ValueError: If stored values are not within ``{0, 255}``.
    """
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError(f"cannot read mask: {path}")
    if not set(np.unique(img).tolist()) <= {0, 255}:
        raise ValueError(f"mask is not binary: {path}")
    return img


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON object as a line; durable on all platforms.

    Args:
        path: Destination ``.jsonl`` file (parents created).
        record: Dict serialized with sorted keys, ASCII-safe.

    Raises:
        OSError: If the file cannot be opened or fsynced.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n"
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read every JSON object from a ``.jsonl`` file, in file order.

    Args:
        path: Source file; missing files yield ``[]``. Blank lines are
            skipped.

    Returns:
        List of parsed dicts in file order.
    """
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def latest_proposals(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Keep the LAST record per sha256 (file order, last line wins).

    Args:
        records: Parsed proposal records; missing ``sha256`` raises.

    Returns:
        Mapping sha256 -> record.

    Raises:
        KeyError: If a record lacks ``sha256`` (corrupt log).
    """
    out: dict[str, dict[str, Any]] = {}
    for rec in records:
        out[str(rec["sha256"])] = rec
    return out


def latest_decisions(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Keep the LAST decision per sha256 (file order, last line wins).

    Args:
        records: Parsed decision records; missing ``sha256`` raises.

    Returns:
        Mapping sha256 -> record.

    Raises:
        KeyError: If a record lacks ``sha256`` (corrupt log).
    """
    out: dict[str, dict[str, Any]] = {}
    for rec in records:
        out[str(rec["sha256"])] = rec
    return out
