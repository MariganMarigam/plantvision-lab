"""Dataset discovery, rasterization, and split-integrity tests."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from plantvision.ml.dataset import (
    SPLITS,
    Sample,
    YoloSegDataset,
    assert_no_leakage,
    discover_samples,
    load_manifest,
    parse_yolo_seg_label,
)
from plantvision.ml.transforms import AugConfig, build_eval_transform, build_train_transform

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data" / "labels" / "farm02-v1"
EXPORT = DATA_ROOT / "export" / "yolo-seg"
MANIFEST = DATA_ROOT / "manifest.csv"

requires_data = pytest.mark.skipif(
    not EXPORT.is_dir() or not MANIFEST.is_file(),
    reason="farm-02 yolo-seg export is absent (data/labels is gitignored)",
)


def _write_label(path: Path, text: str) -> Path:
    """Write one label file and return its path."""
    path.write_text(text, encoding="utf-8")
    return path


@requires_data
def test_discover_samples_counts() -> None:
    """Exported splits have the expected counts and sorted stems."""
    manifest = load_manifest(MANIFEST)
    splits = {split: discover_samples(EXPORT, split, manifest) for split in SPLITS}
    assert {split: len(samples) for split, samples in splits.items()} == {
        "train": 188,
        "val": 83,
        "test": 149,
    }
    for split, samples in splits.items():
        stems = [sample.sha256 for sample in samples]
        assert stems == sorted(stems)
        assert [sample.label_path.name for sample in samples] == [
            f"{stem}.txt" for stem in stems
        ]
        assert all(sample.split == split for sample in samples)


@requires_data
def test_splits_are_disjoint() -> None:
    """No frame or capture group is shared between splits."""
    manifest = load_manifest(MANIFEST)
    splits = {split: discover_samples(EXPORT, split, manifest) for split in SPLITS}
    assert_no_leakage(splits)
    for left in SPLITS:
        for right in SPLITS:
            if left >= right:
                continue
            assert not ({s.sha256 for s in splits[left]} & {s.sha256 for s in splits[right]})
            assert not (
                {s.group_key for s in splits[left]} & {s.group_key for s in splits[right]}
            )


def test_load_manifest_requires_columns(tmp_path: Path) -> None:
    """A manifest without the required columns is rejected."""
    path = tmp_path / "manifest.csv"
    path.write_text("sha256,split\nabc,train\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        load_manifest(path)


def test_parse_exact_rectangle(tmp_path: Path) -> None:
    """A quarter-inset rectangle rasterizes to its exact pixel area."""
    label = _write_label(
        tmp_path / "rect.txt", "0 0.25 0.25 0.75 0.25 0.75 0.75 0.25 0.75\n"
    )
    mask = parse_yolo_seg_label(label, width=101, height=101)
    assert mask.dtype == np.uint8
    assert mask.shape == (101, 101)
    assert int(mask.sum()) == 2601 * 255
    assert set(np.unique(mask).tolist()) == {0, 255}


def test_parse_reaches_last_pixel(tmp_path: Path) -> None:
    """A vertex at (1.0, 1.0) reaches pixel (height-1, width-1)."""
    label = _write_label(tmp_path / "tri.txt", "0 0.0 0.0 1.0 0.0 1.0 1.0\n")
    mask = parse_yolo_seg_label(label, width=101, height=101)
    assert mask[100, 100] == 255


@pytest.mark.parametrize(
    "text",
    [
        "1 0.1 0.1 0.2 0.1 0.2 0.2",
        "0 0.1 0.1 0.2 0.1 0.2",
        "0 0.0 0.0 1.2 0.1 1.0 1.0",
        "",
        "\n \n",
    ],
    ids=["class", "odd-coords", "out-of-range", "empty", "blank"],
)
def test_parse_rejects_bad_input(tmp_path: Path, text: str) -> None:
    """Foreign classes, odd/out-of-range coordinates, and empty labels raise."""
    label = _write_label(tmp_path / "bad.txt", text)
    with pytest.raises(ValueError) as excinfo:
        parse_yolo_seg_label(label, width=101, height=101)
    assert str(label) in str(excinfo.value)


def test_discover_missing_label_raises(tmp_path: Path) -> None:
    """An image without its label file raises FileNotFoundError."""
    (tmp_path / "images" / "train").mkdir(parents=True)
    (tmp_path / "labels" / "train").mkdir(parents=True)
    (tmp_path / "images" / "train" / "abc.jpg").write_bytes(b"not-an-image")
    manifest = {
        "abc": {
            "sha256": "abc",
            "split": "train",
            "group_key": "g",
            "captured_at": "2026-10-24T00:00:00Z",
            "accepted": "1",
        }
    }
    with pytest.raises(FileNotFoundError, match="missing label"):
        discover_samples(tmp_path, "train", manifest)


@requires_data
def test_dataset_item_shapes() -> None:
    """One real sample yields model-sized tensors and the native label."""
    pytest.importorskip("torch")
    manifest = load_manifest(MANIFEST)
    samples = discover_samples(EXPORT, "train", manifest)
    dataset = YoloSegDataset(
        samples,
        image_size=(512, 288),
        transform=build_train_transform(AugConfig(image_size=(512, 288))),
        return_native_mask=True,
        expected_image_size=(1280, 720),
    )
    item = dataset[0]
    assert tuple(item["image"].shape) == (3, 512, 288)
    assert tuple(item["mask"].shape) == (1, 512, 288)
    assert set(np.unique(item["mask"].numpy()).tolist()) <= {0.0, 1.0}
    assert tuple(item["mask_native"].shape) == (1280, 720)


def test_dataset_rejects_wrong_resolution(tmp_path: Path) -> None:
    """A non-1280x720 image is rejected instead of silently resized."""
    image_path = tmp_path / "small.jpg"
    cv2.imwrite(str(image_path), np.zeros((32, 64, 3), dtype=np.uint8))
    label_path = _write_label(
        tmp_path / "small.txt", "0 0.1 0.1 0.9 0.1 0.9 0.9 0.1 0.9\n"
    )
    sample = Sample(
        sha256="small",
        image_path=image_path,
        label_path=label_path,
        split="train",
        group_key="g",
        captured_at="2026-10-24T00:00:00Z",
    )
    dataset = YoloSegDataset(
        [sample], image_size=(512, 288), transform=build_eval_transform((512, 288))
    )
    with pytest.raises(ValueError, match="shape"):
        dataset[0]
