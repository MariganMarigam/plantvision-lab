"""Frame scanning keyed by content hash (plan Section 6 Step 2)."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from plantvision.labeling.frames import (
    FrameRecord,
    file_sha256,
    group_key_for,
    load_frames,
)

KNOWN_SHA_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def _sidecar(
    sha256: str,
    captured_at: str,
    camera_id: str = "phone-01",
    zone_id: str = "shelf-a_tray-1",
    width: int = 20,
    height: int = 10,
) -> dict:
    return {
        "sha256": sha256,
        "captured_at": captured_at,
        "camera_id": camera_id,
        "zone_id": zone_id,
        "width": width,
        "height": height,
    }


def _write_frame(
    base: Path,
    *,
    relpath: str,
    sidecar_sha: str | None = None,
    sidecar_overrides: dict | None = None,
    omit_sidecar: bool = False,
) -> Path:
    folder = base / Path(relpath).parent
    folder.mkdir(parents=True, exist_ok=True)
    jpg = folder / Path(relpath).name
    img = np.zeros((10, 20, 3), dtype=np.uint8)
    assert cv2.imwrite(str(jpg), img)
    if not omit_sidecar:
        import hashlib

        sidecar = _sidecar(
            sidecar_sha or hashlib.sha256(jpg.read_bytes()).hexdigest(),
            "2026-10-16T09:00:00+00:00",
        )
        if sidecar_overrides:
            sidecar.update(sidecar_overrides)
        (jpg.with_suffix(".json")).write_text(
            json.dumps(sidecar), encoding="utf-8"
        )
    return jpg


def test_file_sha256_matches_known_bytes(tmp_path: Path) -> None:
    file = tmp_path / "abc.bin"
    file.write_bytes(b"abc")
    assert file_sha256(file) == KNOWN_SHA_ABC


def test_load_frames_sorted_by_capture_then_sha(tmp_path: Path) -> None:
    """Records come back sorted by (captured_at, sha256); skipped = 0."""
    tmp = tmp_path / "phone-01" / "shelf-a_tray-1" / "2026-10-16"
    tmp.mkdir(parents=True, exist_ok=True)
    img_two = np.zeros((10, 20, 3), dtype=np.uint8)
    img_two[0, 0] = (255, 255, 255)
    assert cv2.imwrite(str(tmp / "f_two.jpg"), img_two)
    assert cv2.imwrite(str(tmp / "f_one.jpg"), np.zeros((10, 20, 3), dtype=np.uint8))
    side_a = _sidecar(0, "2026-10-16T09:00:00+00:00")
    side_a["sha256"] = file_sha256(tmp / "f_one.jpg")
    side_b = _sidecar(0, "2026-10-16T11:00:00+00:00")
    side_b["sha256"] = file_sha256(tmp / "f_two.jpg")
    (tmp / "f_one.json").write_text(json.dumps(side_a), encoding="utf-8")
    (tmp / "f_two.json").write_text(json.dumps(side_b), encoding="utf-8")
    records, skipped = load_frames(tmp_path)
    assert skipped == 0
    assert len(records) == 2
    assert all(isinstance(r, FrameRecord) for r in records)
    assert [r.captured_at for r in records] == [
        "2026-10-16T09:00:00+00:00",
        "2026-10-16T11:00:00+00:00",
    ]
    assert all(r.width == 20 and r.height == 10 for r in records)
    assert all(r.relpath.endswith(".jpg") and "\\" not in r.relpath for r in records)
    assert records[0].sha256 != records[1].sha256
    assert {r.sha256 for r in records} == {
        file_sha256(tmp_path / "phone-01" / "shelf-a_tray-1" / "2026-10-16" / f)
        for f in ("f_one.jpg", "f_two.jpg")
    }


def test_load_frames_skips_missing_sidecar_and_counts(tmp_path: Path) -> None:
    _write_frame(
        tmp_path,
        relpath="phone-01/shelf-a_tray-1/2026-10-16/with_sidecar.jpg",
    )
    _write_frame(
        tmp_path,
        relpath="phone-01/shelf-a_tray-1/2026-10-16/orphan.jpg",
        omit_sidecar=True,
    )
    records, skipped = load_frames(tmp_path)
    assert skipped == 1
    assert len(records) == 1
    assert records[0].relpath.endswith("with_sidecar.jpg")


def test_load_frames_warns_on_sidecar_sha_mismatch(
    tmp_path: Path, recwarn
) -> None:
    _write_frame(
        tmp_path,
        relpath="phone-01/shelf-a_tray-1/2026-10-16/bad_sha.jpg",
        sidecar_sha="0" * 64,
    )
    with __import__("pytest").warns(UserWarning, match="sidecar sha mismatch"):
        records, _ = load_frames(tmp_path)
    jpg = tmp_path / "phone-01" / "shelf-a_tray-1" / "2026-10-16" / "bad_sha.jpg"
    assert records[0].sha256 == file_sha256(jpg)


def test_group_key_replaces_slashes_in_zone() -> None:
    sidecar = {"camera_id": "farm-01", "zone_id": "farm/zone-a"}
    assert group_key_for(sidecar, "2026-10-18T06:00:00+00:00") == (
        "farm-01/farm_zone-a/2026-10-18"
    )


def test_load_frames_empty_dir(tmp_path: Path) -> None:
    assert load_frames(tmp_path) == ([], 0)
