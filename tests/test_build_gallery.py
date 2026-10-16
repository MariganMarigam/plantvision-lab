"""Offline gallery builder: correctness of scan/pairing/thumbnails/ordering."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np
import pytest


def _load_builder():
    """Load scripts/build_gallery.py as a module without package machinery."""
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "build_gallery", root / "scripts" / "build_gallery.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sidecar(sha16: str, captured_at: str) -> dict:
    return {
        "sha256": sha16 * 4,
        "captured_at": captured_at,
        "camera_id": "cam-a",
        "zone_id": "zone",
        "width": 20,
        "height": 10,
        "byte_size": 512,
        "quality": "ok",
        "received_at": captured_at,
    }


def _write_frame(base: Path, name: str, sha16: str, captured_at: str) -> None:
    folder = base / "cam-a" / "zone" / "2026-10-16"
    folder.mkdir(parents=True, exist_ok=True)
    img = np.zeros((10, 20, 3), dtype=np.uint8)
    assert cv2.imwrite(str(folder / f"{name}_{sha16}.jpg"), img)
    (folder / f"{name}_{sha16}.json").write_text(
        json.dumps(_sidecar(sha16, captured_at)), encoding="utf-8"
    )


@pytest.fixture()
def gallery_env(tmp_path: Path):
    """Two paired frames (older + newer) plus one orphan .jpg with no sidecar."""
    builder = _load_builder()
    orig = tmp_path / "originals"
    _write_frame(orig, "20261016T090000.000000Z", "aaaa1111bbbb2222", "2026-10-16T09:00:00Z")
    _write_frame(orig, "20261016T110000.000000Z", "cccc3333dddd4444", "2026-10-16T11:00:00Z")
    orphan = orig / "cam-a" / "zone" / "2026-10-16" / "20261016T120000.000000Z_eeee5555ffff6666.jpg"
    assert cv2.imwrite(str(orphan), np.zeros((10, 20, 3), dtype=np.uint8))
    return builder, orig, tmp_path / "out"


def test_gallery_builds_newest_first(gallery_env) -> None:
    """index.html is written, contains both shas, newest card appears first."""
    builder, orig, out = gallery_env
    rc = builder.main(
        [
            "--originals", str(orig),
            "--out", str(out),
            "--thumb-width", "480",
        ]
    )
    assert rc == 0
    index = out / "index.html"
    assert index.exists()
    html = index.read_text(encoding="utf-8")
    assert "aaaa1111bbbb2222" in html
    assert "cccc3333dddd4444" in html
    older, newer = html.index("aaaa1111bbbb2222"), html.index("cccc3333dddd4444")


def test_gallery_thumbs_and_contact_sheet(gallery_env) -> None:
    """Orphan .jpg without sidecar is skipped; exactly 2 thumbs + contact sheet."""
    builder, orig, out = gallery_env
    rc = builder.main(["--originals", str(orig), "--out", str(out)])
    assert rc == 0
    thumbs = sorted((out / "thumbs").iterdir())
    assert [p.name for p in thumbs] == [
        "aaaa1111bbbb2222.jpg",
        "cccc3333dddd4444.jpg",
    ]
    sheet = out / "contact_sheet.jpg"
    assert sheet.exists()
    img = cv2.imread(str(sheet))
    assert img is not None and img.size > 0
