"""YOLO-seg dataset discovery, native rasterization, and split integrity."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

import cv2
import numpy as np

SPLITS: tuple[str, str, str] = ("train", "val", "test")

MANIFEST_COLUMNS: tuple[str, ...] = (
    "sha256",
    "split",
    "group_key",
    "captured_at",
    "accepted",
)


@dataclass(frozen=True)
class Sample:
    """One exported frame: image, label, and its manifest provenance."""

    sha256: str
    image_path: Path
    label_path: Path
    split: str
    group_key: str
    captured_at: str


def load_manifest(path: Path) -> dict[str, dict[str, str]]:
    """Load ``manifest.csv`` keyed by frame sha256.

    Args:
        path: Path to ``manifest.csv``.

    Returns:
        Mapping ``sha256 -> row``; a duplicate sha keeps the last row.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If a required column is missing.
    """
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = tuple(reader.fieldnames or ())
        missing = [column for column in MANIFEST_COLUMNS if column not in fields]
        if missing:
            raise ValueError(f"manifest {path} missing columns: {missing}")
        return {row["sha256"]: dict(row) for row in reader}


def discover_samples(
    root: Path, split: str, manifest: Mapping[str, Mapping[str, str]]
) -> list[Sample]:
    """List the exported samples of one split, joined with the manifest.

    Args:
        root: YOLO-seg export root (contains ``images/`` and ``labels/``).
        split: One of :data:`SPLITS`.
        manifest: Mapping returned by :func:`load_manifest`.

    Returns:
        Samples sorted by image path.

    Raises:
        ValueError: Unknown split, missing/foreign/non-accepted manifest row.
        FileNotFoundError: Missing split directory or label file.
    """
    if split not in SPLITS:
        raise ValueError(f"unknown split: {split!r}")
    image_dir = root / "images" / split
    label_dir = root / "labels" / split
    for directory in (image_dir, label_dir):
        if not directory.is_dir():
            raise FileNotFoundError(f"missing split directory: {directory}")
    samples: list[Sample] = []
    for image_path in sorted(image_dir.glob("*.jpg")):
        label_path = label_dir / f"{image_path.stem}.txt"
        if not label_path.is_file():
            raise FileNotFoundError(
                f"missing label {label_path} for image {image_path}"
            )
        samples.append(_sample_from_row(image_path, label_path, split, manifest))
    return samples


def _sample_from_row(
    image_path: Path,
    label_path: Path,
    split: str,
    manifest: Mapping[str, Mapping[str, str]],
) -> Sample:
    """Build one :class:`Sample`, validating its manifest row."""
    row = manifest.get(image_path.stem)
    if row is None:
        raise ValueError(
            f"no manifest row for image stem {image_path.stem} ({image_path})"
        )
    if row.get("accepted") != "1":
        raise ValueError(f"manifest row not accepted: {image_path.stem} ({image_path})")
    if row.get("split") != split:
        raise ValueError(
            f"split mismatch for {image_path.stem}: manifest={row.get('split')!r} "
            f"expected={split!r}"
        )
    return Sample(
        sha256=image_path.stem,
        image_path=image_path,
        label_path=label_path,
        split=split,
        group_key=row.get("group_key", ""),
        captured_at=row.get("captured_at", ""),
    )


def parse_yolo_seg_label(
    label_path: Path, *, width: int, height: int, class_id: int = 0
) -> np.ndarray:
    """Rasterize a YOLO-seg polygon label at native resolution.

    Coordinates are de-normalized with ``(width - 1, height - 1)``, inverting
    the exporter convention.

    Args:
        label_path: ``.txt`` label file with one polygon per line.
        width: Frame width in pixels.
        height: Frame height in pixels.
        class_id: Required class id; other ids raise.

    Returns:
        ``(height, width)`` uint8 mask with values in ``{0, 255}``.

    Raises:
        FileNotFoundError: If ``label_path`` does not exist.
        ValueError: Empty label, foreign class, malformed or out-of-range
            coordinates.
    """
    text = label_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"empty label: {label_path}")
    mask = np.zeros((height, width), dtype=np.uint8)
    for line in lines:
        parts = line.split()
        if int(parts[0]) != class_id:
            raise ValueError(f"class id {parts[0]!r} != {class_id} in {label_path}")
        points = _label_points(parts[1:], label_path, width=width, height=height)
        polygon = np.zeros_like(mask)
        cv2.fillPoly(polygon, [points], 255)
        mask = cv2.bitwise_or(mask, polygon)
    return mask


def _label_points(
    tokens: Sequence[str], label_path: Path, *, width: int, height: int
) -> np.ndarray:
    """Parse one label line's coordinate tokens into integer pixel vertices."""
    coords = np.asarray(tokens, dtype=np.float64)
    if len(coords) < 6 or len(coords) % 2 != 0:
        raise ValueError(
            f"label needs an even coordinate count >= 6 in {label_path}: "
            f"{' '.join(tokens)[:40]!r}"
        )
    if np.any(coords < -1e-6) or np.any(coords > 1 + 1e-6):
        raise ValueError(f"label coordinate outside [0, 1] in {label_path}")
    scale = np.asarray([width - 1, height - 1], dtype=np.float64)
    return np.rint(coords.reshape(-1, 2) * scale).astype(np.int32)


def assert_no_leakage(splits: Mapping[str, Sequence[Sample]]) -> None:
    """Assert that exported splits share no frame and no capture group.

    Args:
        splits: Mapping ``split -> samples``; only :data:`SPLITS` keys count.

    Raises:
        ValueError: Overlapping ``sha256`` or ``group_key`` values, or an
            empty ``train``/``val``/``test`` split.
    """
    names = [name for name in SPLITS if name in splits]
    for position, left in enumerate(names):
        for right in names[position + 1 :]:
            for field in ("sha256", "group_key"):
                overlap = {getattr(s, field) for s in splits[left]} & {
                    getattr(s, field) for s in splits[right]
                }
                if overlap:
                    raise ValueError(
                        f"{field} overlap between {left} and {right}: "
                        f"{sorted(overlap)[:5]}"
                    )
    for name in ("train", "val"):
        if not splits.get(name):
            raise ValueError(f"no samples for split {name!r}")
    if "test" in splits and not splits["test"]:
        raise ValueError("no samples for split 'test'")


class YoloSegDataset:
    """Torch dataset over exported YOLO-seg frames.

    Torch is imported inside :meth:`__getitem__` so that importing this module
    never loads torch.
    """

    def __init__(
        self,
        samples: Sequence[Sample],
        *,
        image_size: tuple[int, int] = (288, 512),
        transform: Callable[..., dict] | None = None,
        return_native_mask: bool = False,
        expected_image_size: tuple[int, int] = (720, 1280),
    ) -> None:
        """Store the sample list and loader options.

        Args:
            samples: Samples of one split.
            image_size: Model input ``(H, W)``; applied by ``transform``.
            transform: Callable taking ``image=`` (RGB) and ``mask=``.
            return_native_mask: Also return the ``(720, 1280)`` label mask.
            expected_image_size: Required native ``(H, W)`` of every image.
        """
        self.samples = list(samples)
        self.image_size = image_size
        self.transform = transform
        self.return_native_mask = return_native_mask
        self.expected_image_size = expected_image_size

    def __len__(self) -> int:
        """Number of samples in the split."""
        return len(self.samples)

    def __getitem__(self, index: int) -> dict[str, object]:
        """Load, transform, and tensorize one sample.

        Args:
            index: Position in the sample list.

        Returns:
            Dict with ``image``, ``mask``, ``sha256``, and optionally
            ``mask_native``.

        Raises:
            FileNotFoundError: Image unreadable or missing.
            ValueError: Wrong resolution or missing transform.
        """
        sample = self.samples[index]
        image = cv2.imread(str(sample.image_path))
        if image is None:
            raise FileNotFoundError(f"cannot read image: {sample.image_path}")
        expected = (*self.expected_image_size, 3)
        if image.shape != expected:
            raise ValueError(
                f"image {sample.image_path} has shape {image.shape}, expected {expected}"
            )
        height, width = image.shape[:2]
        native = parse_yolo_seg_label(sample.label_path, width=width, height=height)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if self.transform is None:
            raise ValueError("transform is required")
        out = self.transform(image=rgb, mask=native)
        import torch

        mask = out["mask"].float().div(255).unsqueeze(0)
        item: dict[str, object] = {
            "image": out["image"],
            "mask": mask,
            "sha256": sample.sha256,
        }
        if self.return_native_mask:
            item["mask_native"] = torch.from_numpy(native)
        return item
