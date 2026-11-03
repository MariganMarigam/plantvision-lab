"""Build canonical time-series rows from SAM2 proposals + PNG masks.

The node is deliberately free of model code: it reads the proposal JSONL that
``scripts/label_sam2.py`` produced, the exported PNG masks and the original
frames, then reuses the existing perception helpers (ArUco scale + shape
traits) to produce rows for ``plantvision.analytics.timeseries``. No ``torch``
import exists on this path.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import cv2

from plantvision.analytics.timeseries import FrameRecord, format_row
from plantvision.vision.metrics import FrameMeasurement
from plantvision.vision.scale import px_per_mm
from plantvision.vision.traits import compute_traits

REQUIRED_KEYS: tuple[str, ...] = (
    "sha256", "captured_at", "frame_relpath", "mask_relpath", "area_fraction",
    "box_source", "width", "height", "score",
)

_ROW_COUNTERS: dict[str, str] = {
    "frame": "missing_frame",
    "sidecar": "missing_sidecar",
    "mask": "missing_mask",
    "read": "read_error",
}


@dataclass(frozen=True)
class Proposal:
    """One SAM2 proposal, reduced to the fields the row builder needs."""

    sha256: str
    captured_at: str
    frame_relpath: str
    mask_relpath: str
    box_source: str
    width: int
    height: int


class SeriesRowError(Exception):
    """A single row could not be built; ``kind`` selects the summary counter."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class SeriesBuildResult:
    """Rows plus the deterministic exclusion/error counters for one build."""

    rows: tuple[dict[str, str], ...]
    proposals: int
    excluded_rejected: int
    excluded_review: int
    missing_review: int
    missing_frame: int
    missing_mask: int
    missing_sidecar: int
    read_error: int
    scale_rows: int
    trait_rows: int
    errors: tuple[str, ...]


def read_proposals(path: str | Path) -> list[Proposal]:
    """Read proposal JSONL lines into :class:`Proposal` objects.

    Args:
        path: ``proposals.jsonl`` path.

    Returns:
        Proposals in file order.

    Raises:
        ValueError: On invalid JSON, a missing required key, non-integer
            width/height, or a duplicate ``sha256``.
        OSError: If the file cannot be read.
    """
    proposals: list[Proposal] = []
    seen: set[str] = set()
    with Path(path).open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"proposal line {number}: invalid JSON") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"proposal line {number}: expected a JSON object")
            for key in REQUIRED_KEYS:
                if key not in obj:
                    raise ValueError(f"proposal line {number}: missing key {key}")
            try:
                width = int(obj["width"])
                height = int(obj["height"])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"proposal line {number}: width/height not integers"
                ) from exc
            sha = str(obj["sha256"])
            if sha in seen:
                raise ValueError(f"proposal line {number}: duplicate sha256 {sha}")
            seen.add(sha)
            proposals.append(
                Proposal(
                    sha256=sha,
                    captured_at=str(obj["captured_at"]),
                    frame_relpath=str(obj["frame_relpath"]),
                    mask_relpath=str(obj["mask_relpath"]),
                    box_source=str(obj["box_source"]),
                    width=width,
                    height=height,
                )
            )
    return proposals


def read_review_status(path: str | Path) -> dict[str, str]:
    """Read the manifest's ``sha256 -> accepted`` map.

    Args:
        path: ``manifest.csv`` path.

    Returns:
        Mapping of sha256 to ``"0"``, ``"1"`` or ``""``.

    Raises:
        ValueError: If a required column is missing or a value is not one of
            ``{"0", "1", ""}``.
        OSError: If the file cannot be read.
    """
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or ())
        for required in ("sha256", "accepted"):
            if required not in columns:
                raise ValueError(f"manifest missing column {required}")
        review: dict[str, str] = {}
        for row in reader:
            sha = (row.get("sha256") or "").strip()
            value = (row.get("accepted") or "").strip()
            if value not in {"0", "1", ""}:
                raise ValueError(f"manifest {sha}: accepted={value!r}")
            review[sha] = value
    return review


def measure_row(
    proposal: Proposal,
    *,
    originals_root: str | Path,
    labels_root: str | Path,
    marker_size_mm: float,
    aruco_dict: str,
    biosource_id: str,
    experiment_id: str,
    observation_unit_id: str,
    pending: bool,
) -> dict[str, str]:
    """Measure one proposal and return its canonical CSV row.

    Args:
        proposal: Proposal to measure.
        originals_root: Root of the originals tree (``frame_relpath`` base).
        labels_root: Root of the label export (``mask_relpath`` base).
        marker_size_mm: Printed ArUco marker side in millimetres.
        aruco_dict: Predefined OpenCV ArUco dictionary name.
        biosource_id: Crop id written to the row.
        experiment_id: Experiment id written to the row.
        observation_unit_id: Observation unit id written to the row.
        pending: Whether the proposal still awaits human review.

    Returns:
        A ``TIMESERIES_COLUMNS``-keyed string row.

    Raises:
        SeriesRowError: When the frame/mask/sidecar is missing or unreadable.
    """
    sha = proposal.sha256
    frame = Path(originals_root) / proposal.frame_relpath
    sidecar_path = frame.with_suffix(".json")
    mask_path = Path(labels_root) / proposal.mask_relpath
    if not frame.is_file():
        raise SeriesRowError("frame", f"{sha}: missing frame {frame}")
    if not sidecar_path.is_file():
        raise SeriesRowError("sidecar", f"{sha}: missing sidecar {sidecar_path}")
    if not mask_path.is_file():
        raise SeriesRowError("mask", f"{sha}: missing mask {mask_path}")

    gray = cv2.imread(str(frame), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise SeriesRowError("read", f"{sha}: cannot decode frame {frame}")
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise SeriesRowError("read", f"{sha}: cannot decode mask {mask_path}")
    try:
        side = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SeriesRowError("read", f"{sha}: unreadable sidecar {sidecar_path}") from exc

    ppm = px_per_mm(gray, marker_size_mm, aruco_dict)
    area = int(cv2.countNonZero(mask))
    traits = compute_traits(mask)
    _x, _y, bbox_w, bbox_h = cv2.boundingRect(mask)
    width = proposal.width if proposal.width > 0 else int(mask.shape[1])
    height = proposal.height if proposal.height > 0 else int(mask.shape[0])

    camera_id = str(side.get("camera_id") or "")
    if not camera_id:
        raise SeriesRowError("read", f"{sha}: sidecar has no camera_id")
    zone_id = f"{camera_id}/{str(side.get('zone_id') or 'unknown').replace('/', '_')}"
    flags = tuple(str(flag) for flag in (side.get("quality_flags") or ()))
    if pending:
        flags = flags + ("label_pending",)

    measurement = FrameMeasurement(
        stem=sha,
        captured_at=proposal.captured_at,
        px_per_mm=ppm,
        projected_area_px=area,
        projected_area_cm2=None if ppm is None else area / (ppm * ppm) / 100.0,
        roi_fraction_pct=100.0 * area / (width * height) if width * height else 0.0,
        bbox_w=bbox_w,
        bbox_h=bbox_h,
        bbox_w_cm=None,
        bbox_h_cm=None,
        blur_lapvar=float(side.get("blur_lapvar") or 0.0),
        brightness_mean=float(side.get("brightness") or 0.0),
        quality_flags=flags,
        hull_area_px=None if traits is None else traits.hull_area_px,
        solidity=None if traits is None else traits.solidity,
        perimeter_px=None if traits is None else traits.perimeter_px,
        ellipse_major_px=None if traits is None else traits.ellipse_major_px,
        ellipse_minor_px=None if traits is None else traits.ellipse_minor_px,
        extent=None if traits is None else traits.extent,
        n_components=None if traits is None else traits.n_components,
    )
    record = FrameRecord(
        jpg=frame,
        sha256=sha,
        captured_at=proposal.captured_at,
        received_at=side.get("received_at"),
        camera_id=camera_id,
        zone_id=zone_id,
        width=width,
        height=height,
        experiment_id=experiment_id,
        biosource_id=biosource_id,
        observation_unit_id=observation_unit_id,
        settings_source="",
    )
    return format_row(record, measurement)


def build_rows(
    proposals: Sequence[Proposal],
    review: Mapping[str, str],
    *,
    originals_root: str | Path,
    labels_root: str | Path,
    review_status: str = "all",
    marker_size_mm: float = 45.0,
    aruco_dict: str = "DICT_5X5_50",
    biosource_id: str = "",
    experiment_id: str = "farm02-sam2-v1",
    observation_unit_id: str = "farm-02/farm_zone-b",
) -> SeriesBuildResult:
    """Build canonical rows for the selected proposals.

    Args:
        proposals: Proposals in file order.
        review: Manifest ``sha256 -> accepted`` map.
        originals_root: Root of the originals tree.
        labels_root: Root of the label export.
        review_status: ``"all"`` (accepted + pending) or ``"accepted"``.
        marker_size_mm: Printed ArUco marker side in millimetres.
        aruco_dict: Predefined OpenCV ArUco dictionary name.
        biosource_id: Crop id written to every row.
        experiment_id: Experiment id written to every row.
        observation_unit_id: Observation unit id written to every row.

    Returns:
        A :class:`SeriesBuildResult` with rows sorted by
        ``(captured_at, sha256)``.

    Raises:
        ValueError: If ``review_status`` is not supported.
    """
    if review_status not in {"all", "accepted"}:
        raise ValueError(f"unknown review_status {review_status!r}")
    counters = {
        "excluded_rejected": 0,
        "excluded_review": 0,
        "missing_review": 0,
        "missing_frame": 0,
        "missing_mask": 0,
        "missing_sidecar": 0,
        "read_error": 0,
    }
    rows: list[dict[str, str]] = []
    errors: list[str] = []
    scale_rows = 0
    trait_rows = 0
    for proposal in proposals:
        accepted = review.get(proposal.sha256)
        if accepted is None:
            counters["missing_review"] += 1
            accepted = ""
        if accepted == "0":
            counters["excluded_rejected"] += 1
            continue
        if review_status == "accepted" and accepted != "1":
            counters["excluded_review"] += 1
            continue
        try:
            row = measure_row(
                proposal,
                originals_root=originals_root,
                labels_root=labels_root,
                marker_size_mm=marker_size_mm,
                aruco_dict=aruco_dict,
                biosource_id=biosource_id,
                experiment_id=experiment_id,
                observation_unit_id=observation_unit_id,
                pending=accepted == "",
            )
        except SeriesRowError as exc:
            counters[_ROW_COUNTERS[exc.kind]] += 1
            errors.append(str(exc))
            continue
        rows.append(row)
        scale_rows += row["scale_ok"] == "true"
        trait_rows += row["solidity"] != ""

    rows.sort(key=lambda row: (row["captured_at"], row["sha256"]))
    return SeriesBuildResult(
        rows=tuple(rows),
        proposals=len(proposals),
        excluded_rejected=counters["excluded_rejected"],
        excluded_review=counters["excluded_review"],
        missing_review=counters["missing_review"],
        missing_frame=counters["missing_frame"],
        missing_mask=counters["missing_mask"],
        missing_sidecar=counters["missing_sidecar"],
        read_error=counters["read_error"],
        scale_rows=scale_rows,
        trait_rows=trait_rows,
        errors=tuple(errors),
    )
