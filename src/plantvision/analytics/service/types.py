"""Frozen types shared by the analytics data service.

The service is the single authoritative build-time pipeline: it loads CSV rows,
validates them, derives every number, applies validity before rules, joins
results to cards and serialises the versioned payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

from plantvision.analytics.dashboard.contract import FILTERS
from plantvision.analytics.validity import ValidityTable


class GateState(str, Enum):
    """Series-level state resolved before any rule runs."""

    OK = "ok"
    INVALID = "invalid"
    UNPROVEN = "unproven"
    EMPTY = "empty"
    NOT_RECORDED = "not_recorded"


@dataclass(frozen=True)
class ServiceOptions:
    """Global options for one build; invalid values fail loudly."""

    window: str = "all"
    agg: str = "raw"
    mode: str = "abs"
    lang: str = "en"
    include_frames: bool = False
    max_points: int = 240
    title: str = "Plant CV Lab · growth dashboard"

    def __post_init__(self) -> None:
        if self.window not in FILTERS["windows"]:
            raise ValueError(f"unknown window option: {self.window}")
        if self.agg not in FILTERS["aggs"]:
            raise ValueError(f"unknown agg option: {self.agg}")
        if self.mode not in FILTERS["modes"]:
            raise ValueError(f"unknown mode option: {self.mode}")
        if self.lang not in {"en", "ru"}:
            raise ValueError(f"unknown lang option: {self.lang}")
        if self.max_points < 4:
            raise ValueError(f"max_points must be at least 4, got {self.max_points}")
        if not self.title.strip():
            raise ValueError("title must not be empty")


@dataclass(frozen=True)
class SourcePaths:
    """Repository-relative inputs; only :mod:`.load` reads them."""

    validity: Path | None = Path("data/derived/validity.csv")
    alerts: Path | None = Path("data/derived/alerts.json")


@dataclass(frozen=True)
class SourceBundle:
    """Parsed, unfiltered and per-panel rows plus validity and frame data."""

    panels: Sequence[object]
    rows_by_panel: Mapping[str, list[dict[str, str]]]
    raw_rows_by_panel: Mapping[str, list[dict[str, str]]]
    validity: ValidityTable
    frames: Mapping[str, Path] = field(default_factory=dict)
    sidecars: Mapping[str, dict[str, object]] = field(default_factory=dict)
    now: datetime | None = None


@dataclass(frozen=True)
class SeriesBlock:
    """One precomputed metric series with its validity envelope."""

    unit: str
    decimals: int
    measured: int
    missing: int
    source_points: int
    downsampled: bool
    runs: tuple[tuple[tuple[int, float], ...], ...]
    gaps: tuple[tuple[int, int], ...]
    stats: dict[str, float] | None
    condition_key: str = ""
    series_state: str = "empty"
    draw: str = "none"
    validity: Mapping[str, object] = field(default_factory=dict)

    def as_json(self) -> dict[str, object]:
        """Return the JSON-safe payload form."""
        return {
            "unit": self.unit,
            "decimals": self.decimals,
            "measured": self.measured,
            "missing": self.missing,
            "source_points": self.source_points,
            "downsampled": self.downsampled,
            "runs": [
                [[timestamp, round(value, 6)] for timestamp, value in run]
                for run in self.runs
            ],
            "gaps": [[start, end] for start, end in self.gaps],
            "stats": self.stats,
            "condition_key": self.condition_key,
            "series_state": self.series_state,
            "draw": self.draw,
            "validity": dict(self.validity),
        }


@dataclass(frozen=True)
class Gate2Bundle:
    """Everything the page needs from the the v3 service layer."""

    sections: Mapping[str, object]
    cards: Sequence[dict[str, object]]
    svgs: Mapping[str, str]
    findings: Sequence[dict[str, object]]
    legacy: Mapping[str, object]
