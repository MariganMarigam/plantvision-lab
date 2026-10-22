"""YOLO-seg export (plan Section 4.6, Step 10)."""

from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path

from plantvision.labeling.export import (
    export_yolo_seg,
    mask_to_polygon,
    yolo_seg_line,
)
from plantvision.labeling.store import write_mask

SHA_OK = "a" * 64
SHA_BAD = "b" * 64


def _frame_with_rect_mask(tmp_path: Path, sha: str, size: int = 60):
    """Frame JPEG + full-height plant mask in the middle third."""
    img = np.zeros((60, 60, 3), dtype=np.uint8)
    img[:, 20:40] = (0, 255, 0)
    frame_dir = tmp_path / "originals" / "cam-a" / "zone" / "2026-10-16"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame = frame_dir / f"{sha[:8]}.jpg"
    assert cv2.imwrite(str(frame), img)
    mask = np.zeros((60, 60), dtype=np.uint8)
    mask[:, 20:40] = 255
    mask_path = tmp_path / "labels" / "masks" / f"{sha}.png"
    write_mask(mask, mask_path)
    return frame, mask_path


def _row(tmp_path: Path, sha: str, accepted: str, split: str) -> tuple[dict, None]:
    frame, mask_path = _frame_with_rect_mask(tmp_path, sha)
    return (
        {
            "sha256": sha,
            "frame_relpath": frame.relative_to(tmp_path / "originals").as_posix(),
            "mask_relpath": mask_path.relative_to(tmp_path / "labels").as_posix(),
            "accepted": accepted,
            "split": split,
        },
        None,
    )


def test_export_only_accepted_rows(tmp_path: Path) -> None:
    row_ok, _ = _row(tmp_path, SHA_OK, "1", "train")
    row_rejected, _ = _row(tmp_path, SHA_BAD, "0", "train")
    stats = export_yolo_seg(
        [row_ok, row_rejected],
        tmp_path / "originals",
        tmp_path / "labels",
        tmp_path / "out" / "yolo-seg",
        tmp_path / "out" / "png-masks",
    )
    assert stats["exported"] == 1
    assert stats["skipped_degenerate"] == 0
    img = tmp_path / "out" / "yolo-seg" / "images" / "train" / f"{SHA_OK}.jpg"
    lab = tmp_path / "out" / "yolo-seg" / "labels" / "train" / f"{SHA_OK}.txt"
    assert img.exists() and lab.exists()
    assert lab.read_text().startswith("0 ")
    assert not (tmp_path / "out" / "png-masks" / "train" / f"{SHA_BAD}.png").exists()
    assert stats["accepted_missing"] == 0


def test_yolo_line_format() -> None:
    line = yolo_seg_line([(0.0, 0.5), (1.0, 0.25), (0.5, 1.0)])
    assert line == "0 0.000000 0.500000 1.000000 0.250000 0.500000 1.000000"


def test_polygon_normalized_within_unit_square() -> None:
    mask = np.zeros((60, 60), dtype=np.uint8)
    mask[:, 20:41] = 255
    points = mask_to_polygon(mask, 60, 60)
    assert points is not None
    assert len(points) >= 3
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    assert min(xs) >= 0.0 and max(xs) <= 1.0
    assert min(ys) >= 0.0 and max(ys) <= 1.0
    assert abs(min(xs) - 20 / 59) < 0.01
    line = yolo_seg_line(points)
    assert line.startswith("0 ")
    assert len(line.split()) == 1 + 2 * len(points)


def test_data_yaml_has_plant_class(tmp_path: Path) -> None:
    frame, mask_path = _frame_with_rect_mask(tmp_path, SHA_OK)
    row = {
        "sha256": SHA_OK,
        "frame_relpath": frame.relative_to(tmp_path / "originals").as_posix(),
        "mask_relpath": mask_path.relative_to(tmp_path / "labels").as_posix(),
        "accepted": "1",
        "split": "train",
    }
    out = tmp_path / "out" / "yolo-seg"
    export_yolo_seg([row], tmp_path / "originals", tmp_path / "labels",
                    out, tmp_path / "out" / "png-masks")
    text = (out / "data.yaml").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == f"path: {out.as_posix()}"
    assert "train: images/train" in lines
    assert "val: images/val" in lines
    assert "test: images/test" in lines
    assert "names:" in lines
    assert "  0: plant" in lines


def test_degenerate_mask_is_skipped(tmp_path: Path) -> None:
    frame, _ = _frame_with_rect_mask(tmp_path, SHA_OK)
    tiny = np.zeros((60, 60), dtype=np.uint8)
    tiny[0, 0] = 255
    mask_path = tmp_path / "labels" / "masks" / f"{SHA_BAD}.png"
    write_mask(tiny, mask_path)
    row = {
        "sha256": SHA_BAD,
        "frame_relpath": frame.relative_to(tmp_path / "originals").as_posix(),
        "mask_relpath": mask_path.relative_to(tmp_path / "labels").as_posix(),
        "accepted": "1",
        "split": "train",
    }
    out = tmp_path / "out" / "yolo-seg"
    stats = export_yolo_seg([row], tmp_path / "originals", tmp_path / "labels",
                            out, tmp_path / "out" / "png-masks")
    assert stats["skipped_degenerate"] == 1
    assert stats["exported"] == 0
    assert not (out / "labels" / "train" / f"{SHA_BAD}.txt").exists()


def test_png_masks_copied_per_split(tmp_path: Path) -> None:
    for sha, split in ((SHA_OK, "train"), (SHA_BAD, "val")):
        frame, mask_path = _frame_with_rect_mask(tmp_path, sha)
        row = {
            "sha256": sha,
            "frame_relpath": frame.relative_to(
                tmp_path / "originals"
            ).as_posix(),
            "mask_relpath": mask_path.relative_to(
                tmp_path / "labels"
            ).as_posix(),
            "accepted": "1",
            "split": split,
        }
        stats = export_yolo_seg(
            [row], tmp_path / "originals", tmp_path / "labels",
            tmp_path / "out" / "yolo-seg", tmp_path / "out" / "png-masks",
        )
        assert stats["exported"] == 1
        png = tmp_path / "out" / "png-masks" / split / f"{sha}.png"
        assert png.exists()
        stored = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
        assert stored is not None and set(np.unique(stored).tolist()) <= {0, 255}
