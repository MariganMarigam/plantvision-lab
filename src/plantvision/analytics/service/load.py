"""File I/O for the analytics data service.

Only this module reads files. Every other service module is pure and receives
the parsed :class:`SourceBundle`.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from plantvision.analytics.dashboard.legacy import load_rows
from plantvision.analytics.validity import ContractError, load_validity

from .types import SourceBundle, SourcePaths


def _panel_where(panel: object) -> Mapping[str, str]:
    """Read the optional row filter from a panel definition."""
    where = getattr(panel, "where", None)
    return where if isinstance(where, Mapping) else {}


def filter_rows(
    rows: Sequence[dict[str, str]], where: Mapping[str, str] | None
) -> list[dict[str, str]]:
    """Keep rows whose named cells equal the configured values.

    Args:
        rows: Parsed CSV rows.
        where: Column -> required trimmed value map.

    Returns:
        Filtered rows in source order; an empty/absent map returns a copy.
    """
    wanted = {
        name: str(value).strip()
        for name, value in (where or {}).items()
        if str(value).strip()
    }
    if not wanted:
        return list(rows)
    return [
        row
        for row in rows
        if all((row.get(name) or "").strip() == value for name, value in wanted.items())
    ]


def _frame_index(frames_dir: Path | None) -> dict[str, Path]:
    """Index frame files by the first 16 hex chars of their sha256 name."""
    if frames_dir is None or not frames_dir.is_dir():
        return {}
    index: dict[str, Path] = {}
    for path in sorted(frames_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            index[path.stem[:16]] = path
    return index


def _sidecar(first_frame: Path | None) -> dict[str, object]:
    """Read the JSON sidecar next to the first frame when it exists."""
    if first_frame is None:
        return {}
    candidate = first_frame.with_suffix(".json")
    if not candidate.is_file():
        return {}
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_sources(
    panels: Sequence[object],
    sources: SourcePaths,
    *,
    now: datetime | None = None,
) -> SourceBundle:
    """Load every panel CSV, the validity table, frame index and sidecars.

    Args:
        panels: Panel definitions (``id``, ``csv_path``, optional ``where``).
        sources: Repository-relative input paths.
        now: Injected reference time, carried through untouched.

    Returns:
        The parsed source bundle.

    Raises:
        FileNotFoundError: If a panel CSV is missing.
        ContractError: If a CSV header or validity file violates the contract.
    """
    rows_by_panel: dict[str, list[dict[str, str]]] = {}
    raw_rows_by_panel: dict[str, list[dict[str, str]]] = {}
    frames: dict[str, Path] = {}
    sidecars: dict[str, dict[str, object]] = {}
    for panel in panels:
        panel_id = str(getattr(panel, "id", ""))
        csv_path = Path(getattr(panel, "csv_path"))
        try:
            rows = load_rows(csv_path)
        except ValueError as exc:
            raise ContractError(f"{panel_id}: {exc}") from exc
        raw_rows_by_panel[panel_id] = rows
        rows_by_panel[panel_id] = filter_rows(rows, _panel_where(panel))
        index = _frame_index(getattr(panel, "frames_dir", None))
        frames.update(index)
        first = next(iter(index.values()), None)
        sidecars[panel_id] = _sidecar(first)
    return SourceBundle(
        panels=panels,
        rows_by_panel=rows_by_panel,
        raw_rows_by_panel=raw_rows_by_panel,
        validity=load_validity(sources.validity),
        frames=frames,
        sidecars=sidecars,
        now=now,
    )
