"""Frame lookup, deterministic selection, JPEG thumbnails and mask overlay.

``cv2`` is imported lazily inside the rendering functions so importing the
dashboard package never pays the OpenCV cost on a machine that only renders the
legacy page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import numpy as np


def index_frames(frames_dir: Path) -> dict[str, Path]:
    """Index ``*.jpg`` files by the sha16 suffix of their stem.

    Args:
        frames_dir: Originals directory (recursively scanned).

    Returns:
        ``sha16 -> path``; ``{}`` when the directory is absent.
    """
    directory = Path(frames_dir)
    if not directory.is_dir():
        return {}
    index: dict[str, Path] = {}
    for path in sorted(directory.rglob("*.jpg")):
        key = path.stem.rsplit("_", 1)[-1]
        index[key] = path
    return index


def select_frames(
    rows: Sequence[dict[str, str]],
    index: Mapping[str, Path],
    *,
    limit: int = 4,
) -> list[dict[str, str]]:
    """Pick ``limit`` frames spread across a panel's measured window.

    Args:
        rows: Parsed CSV rows.
        index: Frame index from :func:`index_frames`.
        limit: Maximum frames to return.

    Returns:
        Resolvable rows in capture order, deduplicated by sha16.
    """
    if not rows or limit <= 0:
        return []
    resolvable = [
        (position, row)
        for position, row in enumerate(rows)
        if (row.get("sha256") or "")[:16] in index
    ]
    if not resolvable:
        return []
    if len(rows) <= limit:
        chosen = resolvable
    else:
        positions = [
            round(fraction * (len(rows) - 1))
            for fraction in (0.0, 1 / 3, 2 / 3, 1.0)
        ]
        chosen = []
        for position in positions:
            row = rows[position]
            chosen.append((position, row))
        if len({row.get("sha256") for _position, row in chosen}) < limit:
            for position in range(0, len(rows), max(1, len(rows) // max(1, limit))):
                if len({row.get("sha256") for _position, row in chosen}) >= limit:
                    break
                chosen.append((position, rows[position]))
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for position, row in sorted(chosen, key=lambda item: item[0]):
        sha = (row.get("sha256") or "")[:16]
        if sha in seen:
            continue
        seen.add(sha)
        result.append(dict(row))
        if len(result) >= limit:
            break
    return result


def _encode(image: object, quality: int) -> bytes:
    """Encode a BGR image as JPEG bytes."""
    import cv2

    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return bytes(buffer.tobytes())


def render_thumb(path: Path, *, width: int = 288, quality: int = 58) -> bytes:
    """Render a width-constrained JPEG thumbnail.

    Args:
        path: Source JPEG.
        width: Target width in pixels.
        quality: JPEG quality.

    Returns:
        Encoded bytes.

    Raises:
        ValueError: If the source cannot be decoded.
    """
    import cv2

    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"unreadable frame: {path}")
    height = round(image.shape[0] * width / image.shape[1])
    resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    return _encode(resized, quality)


def render_mask_overlay(
    frame_path: Path,
    mask_path: Path,
    *,
    width: int = 480,
    quality: int = 60,
    tint: tuple[int, int, int] = (167, 227, 47),
) -> bytes:
    """Tint masked pixels and render a width-constrained JPEG.

    Args:
        frame_path: Source JPEG.
        mask_path: Binary mask PNG.
        width: Target width in pixels.
        quality: JPEG quality.
        tint: BGR tint applied at 45 % over masked pixels.

    Returns:
        Encoded bytes.

    Raises:
        ValueError: If either file cannot be decoded.
    """
    import cv2

    frame = cv2.imread(str(frame_path))
    if frame is None:
        raise ValueError(f"unreadable frame: {frame_path}")
    mask = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
    if mask is None:
        raise ValueError(f"unreadable mask: {mask_path}")
    if mask.shape[:2] != frame.shape[:2]:
        mask = cv2.resize(
            mask, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_NEAREST
        )
    selected = mask > 0
    output = frame.copy()
    output[selected] = (
        0.55 * frame[selected] + 0.45 * np.array(tint, dtype=np.uint8)
    ).astype(np.uint8)
    height = round(output.shape[0] * width / output.shape[1])
    resized = cv2.resize(output, (width, height), interpolation=cv2.INTER_AREA)
    return _encode(resized, quality)


def frame_alt(panel_label: str, captured_at: str, index: int, total: int) -> str:
    """Build non-empty alt text for one frame thumbnail.

    Args:
        panel_label: Panel display label.
        captured_at: ISO timestamp of the frame.
        index: Zero-based position in the selection.
        total: Number of selected frames.

    Returns:
        The alt string.
    """
    return (
        f"{panel_label} frame {index + 1} of {total}, captured {captured_at}, "
        "thumbnail 288 px wide"
    )
