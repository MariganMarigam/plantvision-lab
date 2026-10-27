"""Persistent per-frame time-series store for the P1 data flywheel.

Loads frame records (jpg + JSON sidecar) from the originals tree, measures
frames not yet present in the store (idempotent by the sidecar ``sha256``),
appends one CSV row per new frame, and regenerates the per-zone projected-area
plots from the full store.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2

from plantvision.analytics.plots import PlotPoint, plot_projected_area
from plantvision.vision.io import ImageReadError, load_image
from plantvision.vision.metrics import (
    FrameMeasurement,
    load_pipeline_config,
    measure_frame,
)

TIMESERIES_COLUMNS: tuple[str, ...] = (
    "sha256", "captured_at", "received_at", "camera_id", "zone_id", "width",
    "height", "px_per_mm", "area_px", "area_cm2", "roi_fraction_pct",
    "bbox_w", "bbox_h", "quality_flag", "scale_ok",
    # P1.5.1 shape traits (appended; blank = not measurable).
    "solidity", "hull_area_px", "hull_area_cm2", "perimeter_px", "perimeter_cm",
    "ellipse_major_px", "ellipse_minor_px", "extent", "n_components",
    # P1.5.2 MIAPPE-lite provenance (appended; blank = absent/null).
    "experiment_id", "biosource_id", "observation_unit_id", "treatment_id",
    "light_regime", "exposure_s", "white_balance", "gain_db", "settings_source",
)

# Float columns -> decimal places in the store; None becomes "".
FLOAT_DECIMALS: dict[str, int] = {
    "px_per_mm": 4, "area_cm2": 3, "roi_fraction_pct": 3,
    "solidity": 4, "hull_area_px": 2, "hull_area_cm2": 3, "perimeter_px": 2,
    "perimeter_cm": 3, "ellipse_major_px": 2, "ellipse_minor_px": 2, "extent": 4,
    "exposure_s": 4, "gain_db": 2,
}

logger = logging.getLogger(__name__)

_SETTING_KEYS: tuple[str, ...] = ("exposure_s", "white_balance", "gain_db")
_SETTING_SOURCES: frozenset[str] = frozenset({"exif", "app", "manual"})


@dataclass(frozen=True)
class FrameRecord:
    """A frame to measure: jpg path plus the sidecar metadata used in rows."""

    jpg: Path
    sha256: str
    captured_at: str | None
    received_at: str | None
    camera_id: str
    zone_id: str
    width: int | None
    height: int | None
    experiment_id: str = ""
    biosource_id: str = ""
    observation_unit_id: str = ""
    treatment_id: str = ""
    light_regime: str = ""
    exposure_s: float | None = None
    white_balance: str = ""
    gain_db: float | None = None
    settings_source: str = ""


@dataclass(frozen=True)
class UpdateResult:
    """Summary of one :func:`run_update` pass."""

    scanned: int
    measured: int
    appended: int
    skipped: int
    errors: int
    rows_total: int
    plot_paths: tuple[Path, ...]


def _read_sidecar(sidecar: Path) -> dict | None:
    """Read a sidecar JSON; ``None`` when malformed/unreadable (caller skips)."""
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _text(value: object) -> str:
    """Render an optional sidecar value as a CSV string (``None`` -> "")."""
    return "" if value is None else str(value)


def _optional_float(meta: dict, key: str) -> float | None:
    """Read an optional numeric sidecar key; absent/``null`` -> ``None``.

    Raises:
        ValueError: If the value is present but not numeric.
    """
    raw = meta.get(key)
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"sidecar {key} is not numeric: {raw!r}") from exc


def _validate_settings(
    exposure_s: float | None,
    white_balance: str,
    gain_db: float | None,
    settings_source: str,
) -> None:
    """Reject a camera setting without a real provenance source.

    Raises:
        ValueError: If a setting is non-null but ``settings_source`` is absent
            or claims ``"unavailable"``.
    """
    present = exposure_s is not None or white_balance != "" or gain_db is not None
    if present and settings_source not in _SETTING_SOURCES:
        raise ValueError(
            "sidecar records a camera setting but settings_source="
            f"{settings_source!r}; a setting without provenance is a false claim"
        )


def load_frame_records(originals_dir: str | Path) -> list[FrameRecord]:
    """Load sidecar-backed frame records from an originals tree.

    Args:
        originals_dir: Root directory searched recursively for ``*.jpg``.

    Returns:
        Records sorted by ``(captured_at is None, captured_at, jpg name)`` —
        frames without a readable sidecar, without a ``sha256``, or with a
        malformed sidecar are skipped (never crash the scan).
    """
    records: list[FrameRecord] = []
    for p in sorted(Path(originals_dir).rglob("*.jpg")):
        sidecar = p.with_suffix(".json")
        if not sidecar.exists():
            continue
        meta = _read_sidecar(sidecar)
        if meta is None:
            continue
        sha = meta.get("sha256")
        if not (isinstance(sha, str) and sha):
            continue
        exposure_s = _optional_float(meta, "exposure_s")
        white_balance = _text(meta.get("white_balance"))
        gain_db = _optional_float(meta, "gain_db")
        settings_source = _text(meta.get("settings_source"))
        _validate_settings(exposure_s, white_balance, gain_db, settings_source)
        records.append(
            FrameRecord(
                jpg=p,
                sha256=sha,
                captured_at=meta.get("captured_at"),
                received_at=meta.get("received_at"),
                camera_id=str(meta.get("camera_id", "")),
                zone_id=str(meta.get("zone_id", "")),
                width=meta.get("width"),
                height=meta.get("height"),
                experiment_id=_text(meta.get("experiment_id")),
                biosource_id=_text(meta.get("biosource_id")),
                observation_unit_id=_text(meta.get("observation_unit_id")),
                treatment_id=_text(meta.get("treatment_id")),
                light_regime=_text(meta.get("light_regime")),
                exposure_s=exposure_s,
                white_balance=white_balance,
                gain_db=gain_db,
                settings_source=settings_source,
            )
        )
    records.sort(key=lambda r: (r.captured_at is None, r.captured_at or "", r.jpg.name))
    return records


def read_timeseries(path: str | Path) -> list[dict[str, str]]:
    """Read the full store; missing file means an empty store.

    Args:
        path: Store CSV path.

    Returns:
        One dict per stored row (string values throughout).
    """
    p = Path(path)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _area_cm2(area_px: float | None, ppm: float | None) -> float | None:
    """Convert a pixel area to cm2 (same convention as ``metrics._cm_metrics``)."""
    if area_px is None or ppm is None:
        return None
    return area_px / (ppm**2) / 100.0


def _length_cm(length_px: float | None, ppm: float | None) -> float | None:
    """Convert a pixel length to cm (same convention as ``metrics._cm_metrics``)."""
    if length_px is None or ppm is None:
        return None
    return length_px / ppm / 10.0


def format_row(record: FrameRecord, meas: FrameMeasurement) -> dict[str, str]:
    """Convert a record + measurement into a TIMESERIES_COLUMNS-ordered row.

    Empty masks (traits ``None``) and missing scale produce blank cells — the
    distinction between "not measurable" and a measured zero is preserved.

    Args:
        record: Sidecar-backed frame record (provenance columns).
        meas: Measurement from :func:`plantvision.vision.metrics.measure_frame`.

    Returns:
        String row; ``None`` float fields become ``""`` and ``scale_ok`` is
        ``true`` iff ``px_per_mm`` was detected.
    """

    def _fmt(value: float | None, decimals: int) -> str:
        return "" if value is None else f"{value:.{decimals}f}"

    return {
        "sha256": record.sha256,
        "captured_at": record.captured_at or "",
        "received_at": record.received_at or "",
        "camera_id": record.camera_id,
        "zone_id": record.zone_id,
        "width": "" if record.width is None else str(record.width),
        "height": "" if record.height is None else str(record.height),
        "px_per_mm": _fmt(meas.px_per_mm, FLOAT_DECIMALS["px_per_mm"]),
        "area_px": str(meas.projected_area_px),
        "area_cm2": _fmt(meas.projected_area_cm2, FLOAT_DECIMALS["area_cm2"]),
        "roi_fraction_pct": _fmt(meas.roi_fraction_pct, FLOAT_DECIMALS["roi_fraction_pct"]),
        "bbox_w": str(meas.bbox_w),
        "bbox_h": str(meas.bbox_h),
        "quality_flag": "|".join(meas.quality_flags),
        "scale_ok": "true" if meas.px_per_mm is not None else "false",
        "solidity": _fmt(meas.solidity, FLOAT_DECIMALS["solidity"]),
        "hull_area_px": _fmt(meas.hull_area_px, FLOAT_DECIMALS["hull_area_px"]),
        "hull_area_cm2": _fmt(
            _area_cm2(meas.hull_area_px, meas.px_per_mm), FLOAT_DECIMALS["hull_area_cm2"]
        ),
        "perimeter_px": _fmt(meas.perimeter_px, FLOAT_DECIMALS["perimeter_px"]),
        "perimeter_cm": _fmt(
            _length_cm(meas.perimeter_px, meas.px_per_mm), FLOAT_DECIMALS["perimeter_cm"]
        ),
        "ellipse_major_px": _fmt(meas.ellipse_major_px, FLOAT_DECIMALS["ellipse_major_px"]),
        "ellipse_minor_px": _fmt(meas.ellipse_minor_px, FLOAT_DECIMALS["ellipse_minor_px"]),
        "extent": _fmt(meas.extent, FLOAT_DECIMALS["extent"]),
        "n_components": "" if meas.n_components is None else str(meas.n_components),
        "experiment_id": record.experiment_id,
        "biosource_id": record.biosource_id,
        "observation_unit_id": record.observation_unit_id,
        "treatment_id": record.treatment_id,
        "light_regime": record.light_regime,
        "exposure_s": _fmt(record.exposure_s, FLOAT_DECIMALS["exposure_s"]),
        "white_balance": record.white_balance,
        "gain_db": _fmt(record.gain_db, FLOAT_DECIMALS["gain_db"]),
        "settings_source": record.settings_source,
    }


def _write_rows_atomic(path: Path, rows: list[list[str]]) -> None:
    """Write all CSV rows through a same-directory temp file + ``os.replace``."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _ensure_header(path: Path) -> None:
    """Migrate a legacy strict-prefix header, or reject a foreign header.

    A file whose header is a strict prefix of :data:`TIMESERIES_COLUMNS` has
    every existing row padded with ``""`` for the appended columns and is
    rewritten atomically. Any other mismatch raises.

    Raises:
        ValueError: If the header is neither exact nor a strict prefix.
        OSError: If the store cannot be read/written.
    """
    if not path.exists() or path.stat().st_size == 0:
        return
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return
    header = tuple(rows[0])
    if header == TIMESERIES_COLUMNS:
        return
    if len(header) < len(TIMESERIES_COLUMNS) and header == TIMESERIES_COLUMNS[: len(header)]:
        new_count = len(TIMESERIES_COLUMNS) - len(header)
        padded = [
            row[: len(header)] + [""] * max(0, len(header) - len(row)) + [""] * new_count
            for row in rows[1:]
        ]
        _write_rows_atomic(path, [list(TIMESERIES_COLUMNS), *padded])
        logger.info("migrated %d rows (+%d columns)", len(padded), new_count)
        return
    raise ValueError(
        f"timeseries header mismatch: file={header} expected={TIMESERIES_COLUMNS}"
    )


def append_rows(path: str | Path, rows: Sequence[dict[str, str]]) -> int:
    """Append rows to the store, writing/migrating the header as needed.

    Args:
        path: Store CSV path (parent dirs created on first write).
        rows: String rows keyed by :data:`TIMESERIES_COLUMNS`.

    Returns:
        Number of rows appended (0 rows appends nothing and creates no file,
        but still migrates an existing legacy header).

    Raises:
        ValueError: If the store's header is not a prefix of
            :data:`TIMESERIES_COLUMNS`.
        OSError: If the store cannot be read/written.
    """
    p = Path(path)
    exists = p.exists() and p.stat().st_size > 0
    if exists:
        _ensure_header(p)
    if not rows:
        return 0
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(TIMESERIES_COLUMNS))
        if not exists:
            writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def points_from_rows(rows: Sequence[dict[str, str]]) -> list[PlotPoint]:
    """Convert stored rows to plot points (bad floats degrade to unscaled)."""
    points: list[PlotPoint] = []
    for r in rows:
        cap = (r.get("captured_at") or "").strip()
        cm = (r.get("area_cm2") or "").strip()
        qf = (r.get("quality_flag") or "").strip()
        try:
            cmv: float | None = float(cm) if cm else None
        except ValueError:
            cmv = None
        points.append(
            PlotPoint(
                captured_at=cap or None,
                projected_area_cm2=cmv,
                quality_flags=tuple(qf.split("|")) if qf else (),
            )
        )
    return points


def run_update(
    originals_dir: str | Path, config_path: str | Path,
    store_path: str | Path, out_dir: str | Path,
) -> UpdateResult:
    """Measure every NEW frame and append it to the store, then re-plot.

    A frame is NEW iff its sidecar ``sha256`` is absent from the store; the
    scan is therefore idempotent (a second pass appends nothing). Undecodable
    jpgs increment ``errors`` and never abort the run. One plot per distinct
    ``zone_id`` is regenerated from the full store.

    Args:
        originals_dir: Root of the originals tree.
        config_path: Path to ``configs/pipeline.yaml``.
        store_path: Time-series CSV path.
        out_dir: Destination directory for the per-zone plots.

    Returns:
        An :class:`UpdateResult` summarizing the pass.

    Raises:
        FileNotFoundError, KeyError, ValueError: Propagated from
            :func:`load_pipeline_config` on a bad/missing config.
        OSError: Propagated from store/plot writes.
    """
    cfg = load_pipeline_config(config_path)
    records = load_frame_records(originals_dir)
    rows = read_timeseries(store_path)
    seen = {r.get("sha256", "") for r in rows}
    seen.discard("")

    measured = skipped = errors = 0
    new_rows: list[dict[str, str]] = []
    for rec in records:
        if rec.sha256 in seen:
            skipped += 1
            continue
        try:
            img = load_image(rec.jpg)
            meas, _mask = measure_frame(img, cfg)
        except (ImageReadError, ValueError, cv2.error):
            errors += 1
            continue
        new_rows.append(format_row(rec, meas))
        seen.add(rec.sha256)
        measured += 1

    appended = append_rows(store_path, new_rows)
    all_rows = rows + new_rows

    zones: dict[str, list[dict[str, str]]] = {}
    for r in all_rows:
        zones.setdefault(r.get("zone_id") or "unknown", []).append(r)
    plot_paths: list[Path] = []
    for zid in sorted(zones):
        slug = zid.replace("/", "_")
        out_png = Path(out_dir) / f"projected-area-{slug}.png"
        plot_projected_area(points_from_rows(zones[zid]), slug, cfg.pipeline_version, out_png)
        plot_paths.append(out_png)

    return UpdateResult(
        scanned=len(records),
        measured=measured,
        appended=appended,
        skipped=skipped,
        errors=errors,
        rows_total=len(all_rows),
        plot_paths=tuple(plot_paths),
    )
