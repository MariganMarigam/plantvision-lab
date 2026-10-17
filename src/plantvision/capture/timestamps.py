"""Time-source precedence for imported frames: exif -> filename -> mtime.

Documented semantics:

- ``exif``: ``DateTimeOriginal`` is the device clock at exposure. If
  ``OffsetTimeOriginal`` exists it is authoritative; otherwise the naive value
  is interpreted in the farm-local tz (``light_window.tz``).
- ``filename``: ``Open Camera`` / timelapse apps name files in the phone's
  LOCAL wall time; interpreted in the farm-local tz. Millisecond-epoch and
  non-date names are not matched and fall through to ``mtime``.
- ``mtime``: absolute POSIX epoch, used as-is (converted to UTC). It is the
  PC-copy last-write time: Windows Explorer / ``Copy-Item`` / ``robocopy``
  preserve the source mtime, but a USB-MTP transfer rewrites it to the
  transfer time. This is why ``mtime`` is last resort AND why ``time_source``
  is persisted in the sidecar - frames whose window decision came from
  ``mtime`` can be excluded later.
- ``tz: local`` resolves to the offset in effect NOW, not at capture time; use
  an explicit ZoneInfo name (e.g. ``"Europe/Berlin"``) when importing across a
  DST boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from plantvision.capture.exif import read_exif_datetime

_FILENAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?P<y>\d{4})(?P<mo>\d{2})(?P<d>\d{2})[_-](?P<h>\d{2})(?P<mi>\d{2})(?P<s>\d{2})"),
    re.compile(r"(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})[T_ ](?P<h>\d{2})[:\-](?P<mi>\d{2})[:\-](?P<s>\d{2})"),
)


@dataclass(frozen=True)
class TimestampGuess:
    """One resolved capture time plus the source that produced it."""

    utc: datetime  # timezone-aware, tzinfo=timezone.utc
    source: str  # "exif" | "filename" | "mtime"


def parse_filename_timestamp(stem: str) -> Optional[datetime]:
    """First plausible farm-local datetime embedded in a filename stem, or None.

    Args:
        stem: Filename without extension, e.g. ``"IMG_20261013_142355"``.

    Returns:
        Naive datetime, or ``None`` when no pattern matches (or the match
        forms an invalid date such as month 13).
    """
    for pattern in _FILENAME_PATTERNS:
        m = pattern.search(stem)
        if m is None:
            continue
        g = {k: int(v) for k, v in m.groupdict().items()}
        try:
            dt = datetime(g["y"], g["mo"], g["d"], g["h"], g["mi"], g["s"])  # month-13 -> next pattern
        except ValueError:
            continue
        if is_plausible(dt):
            return dt
    return None


def resolve_tz(name: str = "local") -> tzinfo:
    """Resolve a timezone name: ``"local"`` = system tz, else a ZoneInfo name.

    Args:
        name: Timezone key from ``light_window.tz``.

    Returns:
        A :class:`datetime.tzinfo`.

    Raises:
        zoneinfo.ZoneInfoNotFoundError: If ``name`` is neither ``"local"``
            nor a valid IANA zone (config error, propagates to the CLI).
    """
    if name == "local":
        return datetime.now().astimezone().tzinfo or timezone.utc
    return ZoneInfo(name)


def parse_offset(offset: str) -> Optional[timezone]:
    """Parse ``"+HH:MM"`` / ``"-HH:MM"`` into a fixed UTC offset, or None."""
    m = re.fullmatch(r"([+-])(\d{2}):(\d{2})", offset)
    if m is None:
        return None
    delta = timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
    return timezone(-delta if m.group(1) == "-" else delta)


def format_utc(dt: datetime) -> str:
    """ISO-8601 UTC with microseconds and a Z suffix (``...T...HH:MM:SS.ffffffZ``)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def is_plausible(dt: datetime) -> bool:
    """True for any datetime whose year lies in 2000..2100."""
    return 2000 <= dt.year <= 2100


def _to_utc(naive: datetime, zone: tzinfo) -> datetime:
    """Attach ``zone`` to a naive value and convert to UTC."""
    return naive.replace(tzinfo=zone).astimezone(timezone.utc)


def resolve_captured_at(data: bytes, path: Path, tz: tzinfo) -> Optional[TimestampGuess]:
    """Resolve the device capture time, trying EXIF, then filename, then mtime.

    Args:
        data: Raw JPEG bytes.
        path: Source file path (stem is scanned for a timestamp; mtime is the
            last resort).
        tz: Farm-local timezone for naive EXIF values without an offset and
            for filename-embedded times.

    Returns:
        A :class:`TimestampGuess` in UTC, or ``None`` when no usable time
        exists (caller logs ``skipped_notime``).
    """
    exif = read_exif_datetime(data)
    if exif is not None:
        naive, offset = exif
        zone = parse_offset(offset) or tz
        return TimestampGuess(_to_utc(naive, zone), "exif")
    fname = parse_filename_timestamp(Path(path).stem)
    if fname is not None:
        return TimestampGuess(_to_utc(fname, tz), "filename")
    try:
        mtime = Path(path).stat().st_mtime
    except OSError:
        return None
    dt = datetime.fromtimestamp(mtime, timezone.utc)
    return TimestampGuess(dt, "mtime") if is_plausible(dt) else None
