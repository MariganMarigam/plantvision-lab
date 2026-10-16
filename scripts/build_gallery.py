"""Build a self-contained HTML gallery of captured frame series.

Scans ``--originals`` for ``<UTC-TS>_<sha16>.jpg`` captures paired with
``<same-stem>.json`` sidecars, writes thumbnails, an ``index.html``
(newest first) and a ``contact_sheet.jpg``. Stdlib + OpenCV only.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

import cv2
import numpy as np

CSS = (
    "body{font-family:system-ui,sans-serif;margin:24px;background:#111;color:#eee}"
    "h1{font-size:1.2rem}h2{font-size:1rem;font-weight:normal;color:#aaa}"
    ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));"
    "gap:16px}"
    ".card{background:#1b1b1b;border-radius:8px;overflow:hidden}"
    ".card img{width:100%;height:auto;display:block}"
    ".card .meta{padding:8px 12px;font-size:0.8rem;line-height:1.5;"
    "word-break:break-all}"
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    p = argparse.ArgumentParser(description="Build gallery from captured frames.")
    p.add_argument("--originals", default="data/originals")
    p.add_argument("--out", default="output/gallery")
    p.add_argument("--thumb-width", type=int, default=480)
    p.add_argument("--title", default="PlantVision — capture gallery")
    return p.parse_args(argv)


def human_size(num_bytes: int) -> str:
    """Format a byte count as human-readable KB/MB."""
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes} B"


def load_frames(originals: Path) -> tuple[list[dict], int]:
    """Pair every .jpg with its .json sidecar, skipping orphans.

    Returns (frames sorted by captured_at descending, skipped orphan count).
    """
    frames, skipped = [], 0
    for jpg_path in sorted(originals.rglob("*.jpg")):
        sidecar_path = jpg_path.with_suffix(".json")
        if not sidecar_path.exists():
            skipped += 1
            continue
        with open(sidecar_path, "r", encoding="utf-8") as f:
            sidecar = json.load(f)
        sha16 = jpg_path.stem.rsplit("_", 1)[-1]
        captured = datetime.fromisoformat(
            str(sidecar["captured_at"]).replace("Z", "+00:00")
        )
        frames.append(
            {
                "jpg": jpg_path,
                "sha16": sha16,
                "captured_at": str(sidecar["captured_at"]),
                "captured_dt": captured,
                "width": int(sidecar["width"]),
                "height": int(sidecar["height"]),
                "byte_size": int(sidecar["byte_size"]),
            }
        )
    frames.sort(key=lambda fr: fr["captured_dt"], reverse=True)
    return frames, skipped


def make_thumbnails(
    frames: list[dict], out: Path, thumb_width: int
) -> None:
    """Write downscaled thumbnails to <out>/thumbs/<sha16>.jpg."""
    thumbs_dir = out / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    for fr in frames:
        img = cv2.imread(str(fr["jpg"]))
        if img is None:
            raise RuntimeError(f"cannot read frame: {fr['jpg']}")
        height = round(img.shape[0] * thumb_width / img.shape[1])
        resized = cv2.resize(img, (thumb_width, height), interpolation=cv2.INTER_AREA)
        dest = thumbs_dir / f"{fr['sha16']}.jpg"
        if not cv2.imwrite(str(dest), resized):
            raise RuntimeError(f"cannot write thumbnail: {dest}")
        fr["thumb_h"] = height


def card_html(fr: dict) -> str:
    """Render one card: thumbnail plus escaped sidecar metadata."""
    meta = html.escape(fr["captured_at"])
    size = html.escape(human_size(fr["byte_size"]))
    name = html.escape(fr["jpg"].name)
    sha = html.escape(fr["sha16"][:12])
    return (
        f'<div class="card"><img src="thumbs/{sha}" alt="{name}">'
        f'<div class="meta">captured_at: {meta}<br>'
        f'size: {fr["width"]}x{fr["height"]} ({size})<br>'
        f'sha: {sha}<br>file: {name}</div></div>'
    )


def write_index(
    frames: list[dict], out: Path, title: str
) -> None:
    """Write self-contained index.html, newest first."""
    count = len(frames)
    newest = html.escape(frames[0]["captured_at"]) if frames else "—"
    cards = "\n".join(card_html(fr) for fr in frames)
    doc = (
        f"<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body>"
        f"<h1>{html.escape(title)}</h1>"
        f"<h2>{count} frames — newest: {newest}</h2>"
        f'<div class="grid">{cards}</div></body></html>'
    )
    (out / "index.html").write_text(doc, encoding="utf-8")


def write_contact_sheet(frames: list[dict], out: Path) -> None:
    """Lay the thumbnails out on a simple grid and save as contact_sheet.jpg."""
    thumbs_dir = out / "thumbs"
    sheet = _grid_of(thumbs_dir, [fr["sha16"] for fr in frames])
    if not cv2.imwrite(str(out / "contact_sheet.jpg"), sheet):
        raise RuntimeError("cannot write contact sheet")


def _grid_of(thumbs_dir: Path, shas: list[str]) -> np.ndarray:
    """Assemble thumbs (padded with gray cells) into one grid array."""
    if not shas:
        return np.zeros((1, 1, 3), dtype=np.uint8)
    imgs = [cv2.imread(str(thumbs_dir / f"{sha}.jpg")) for sha in shas]
    missing = [im for im in imgs if im is None]
    if missing:
        raise RuntimeError("missing thumbnail for contact sheet")
    cols = math.ceil(math.sqrt(len(imgs)))
    rows = math.ceil(len(imgs) / cols)
    cell_w = max(im.shape[1] for im in imgs)
    cell_h = max(im.shape[0] for im in imgs)
    sheet = np.full((rows * cell_h, cols * cell_w, 3), fill_value=40, dtype=np.uint8)
    for i, im in enumerate(imgs):
        r, c = (i // cols) * cell_h, (i % cols) * cell_w
        sheet[r : r + im.shape[0], c : c + im.shape[1]] = im
    return sheet


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entrypoint. Returns 0 on success."""
    args = parse_args(argv)
    originals, out = Path(args.originals), Path(args.out)
    frames, skipped = load_frames(originals)
    make_thumbnails(frames, out, args.thumb_width)
    write_index(frames, out, args.title)
    write_contact_sheet(frames, out)
    print(
        f"gallery: {len(frames)} frames, {skipped} skipped (no sidecar) -> {out}/index.html"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
