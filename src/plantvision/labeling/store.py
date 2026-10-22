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


def _sorted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort manifest rows by ``(captured_at, sha256)`` (idempotent)."""
    return sorted(rows, key=lambda r: (r["captured_at"], r["sha256"]))


def _split_counts(n: int) -> tuple[int, int]:
    """Compute ``(n_train, n_val)`` for n rows under the 70/15/15 rule.

    Uses floor/clamp so every split keeps >= 1 row when n >= 3, and all
    rows fall to train when n < 3 (plan Section 4.5).
    """
    n_train = max(1, int(0.70 * n))
    n_val = max(1, int(0.15 * n))
    if n - n_train - n_val < 1:
        n_train = n - n_val - 1
    return n_train, n_val


def assign_splits(
    rows: list[dict[str, Any]], strategy: str = "temporal"
) -> list[dict[str, Any]]:
    """Assign ``split`` to every row; deterministic, no RNG.

    Args:
        rows: Manifest rows (dicts; sorted by ``(captured_at, sha256)``
            internally, so input order is irrelevant).
        strategy: ``"temporal"`` sorts rows then assigns contiguous
            train/val/test blocks; ``"group"`` assigns whole
            ``group_key`` groups (70/15/15 on the sorted group list).

    Returns:
        The same row dicts (mutated), each with ``split`` set.

    Raises:
        ValueError: If ``strategy`` is unknown, or the group strategy is
            used with fewer than 3 distinct group keys.
    """
    if strategy not in ("temporal", "group"):
        raise ValueError(f"unknown split strategy: {strategy!r}")
    sorted_rows = _sorted_rows(rows)
    if strategy == "temporal":
        n = len(sorted_rows)
        if n < 3:
            for row in sorted_rows:
                row["split"] = "train"
            return sorted_rows
        n_train, n_val = _split_counts(n)
        for i, row in enumerate(sorted_rows):
            if i < n_train:
                row["split"] = "train"
            elif i < n_train + n_val:
                row["split"] = "val"
            else:
                row["split"] = "test"
        return sorted_rows

    groups = sorted({str(r["group_key"]) for r in sorted_rows})
    if len(groups) < 3:
        raise ValueError(
            "group split requires >= 3 distinct group keys, "
            f"got {len(groups)}: {groups}"
        )
    n_groups = len(groups)
    g_train, g_val = _split_counts(n_groups)
    group_train, group_val, group_test = (
        groups[:g_train],
        groups[g_train : g_train + g_val],
        groups[g_train + g_val:],
    )
    for row in sorted_rows:
        g = str(row["group_key"])
        if g in group_train:
            row["split"] = "train"
        elif g in group_val:
            row["split"] = "val"
        else:
            row["split"] = "test"
    return sorted_rows


def build_manifest(
    proposals: list[dict[str, Any]],
    decisions: dict[str, dict[str, Any]],
    strategy: str = "temporal",
) -> list[dict[str, Any]]:
    """Join proposals with decisions into manifest rows with splits.

    Args:
        proposals: Parsed proposal records (last one per sha256 wins;
            requires ``sha256``, ``frame_relpath``, ``mask_relpath``,
            ``score``, ``area_fraction``, ``box``, ``box_source``,
            ``model``, ``checkpoint``, ``created_at``, ``group_key``,
            ``captured_at``).
        decisions: Mapping sha256 -> decision record; decisions for
            unknown shas are ignored.
        strategy: Split strategy forwarded to :func:`assign_splits`.

    Returns:
        Rows with keys exactly :data:`MANIFEST_COLUMNS`, sorted by
        ``(captured_at, sha256)``, splits assigned.

    Raises:
        KeyError: If a proposal record lacks a required key (corrupt log).
        ValueError: Unknown split strategy (documented CLI contract).
    """
    uniq = latest_proposals(proposals)
    rows: list[dict[str, Any]] = []
    for sha, p in uniq.items():
        d = decisions.get(sha)
        accepted = ""
        reject_reason = ""
        reviewer = ""
        reviewed_at = ""
        if d is not None:
            verdict = str(d.get("verdict", ""))
            if verdict == "accept":
                accepted = "1"
            elif verdict == "reject":
                accepted = "0"
                reject_reason = str(d.get("reason", ""))
            reviewer = str(d.get("reviewer", ""))
            reviewed_at = str(d.get("decided_at", ""))
        box = p["box"]
        rows.append(
            {
                "sha256": sha,
                "frame_relpath": p["frame_relpath"],
                "mask_relpath": p["mask_relpath"],
                "accepted": accepted,
                "reject_reason": reject_reason,
                "reviewer": reviewer,
                "reviewed_at": reviewed_at,
                "split": "",
                "group_key": p["group_key"],
                "captured_at": p["captured_at"],
                "confidence": f"{float(p['score']):.4f}",
                "area_fraction": f"{float(p['area_fraction']):.4f}",
                "box": ";".join(str(int(v)) for v in box),
                "box_source": p["box_source"],
                "model": p["model"],
                "checkpoint": p["checkpoint"],
                "created_at": p["created_at"],
            }
        )
    sorted_rows = _sorted_rows(rows)
    return assign_splits(sorted_rows, strategy=strategy)


def write_manifest_csv(rows: list[dict[str, Any]], path: Path) -> Path:
    """Write manifest rows to CSV with the exact column order.

    Args:
        rows: Manifest rows from :func:`build_manifest`.
        path: Destination ``manifest.csv`` (parents created).

    Returns:
        The destination path.

    Raises:
        OSError: If the destination is not writable (propagated).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path
