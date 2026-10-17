"""Unit tests for time-source precedence and formatting (Step 4)."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from plantvision.capture.timestamps import (
    format_utc,
    parse_filename_timestamp,
    parse_offset,
    resolve_captured_at,
)
from tests.exif_fixture import jpeg_bytes, jpeg_with_exif


def test_parse_filename_compact() -> None:
    assert parse_filename_timestamp("IMG_20261013_142355") == datetime(2026, 10, 13, 14, 23, 55)
    assert parse_filename_timestamp("20261013_142355") == datetime(2026, 10, 13, 14, 23, 55)


def test_parse_filename_iso_ish() -> None:
    assert parse_filename_timestamp("2026-10-13_14-23-55") == datetime(2026, 10, 13, 14, 23, 55)


def test_parse_filename_invalid_returns_none() -> None:
    assert parse_filename_timestamp("IMG_20261313_142355") is None
    assert parse_filename_timestamp("frame") is None


def test_resolve_prefers_exif(tmp_path: Path) -> None:
    p = tmp_path / "IMG_20261011_010101.jpg"
    p.write_bytes(jpeg_with_exif("2026:10:13 14:23:55", "+00:00"))
    guess = resolve_captured_at(p.read_bytes(), p, timezone.utc)
    assert guess is not None
    assert guess.source == "exif"
    assert guess.utc == datetime(2026, 10, 13, 14, 23, 55, tzinfo=timezone.utc)


def test_resolve_falls_back_to_filename(tmp_path: Path) -> None:
    p = tmp_path / "IMG_20261013_142355.jpg"
    p.write_bytes(jpeg_bytes())
    guess = resolve_captured_at(p.read_bytes(), p, timezone.utc)
    assert guess is not None
    assert guess.source == "filename"
    assert guess.utc == datetime(2026, 10, 13, 14, 23, 55, tzinfo=timezone.utc)


def test_resolve_falls_back_to_mtime(tmp_path: Path) -> None:
    p = tmp_path / "frame.jpg"
    p.write_bytes(jpeg_bytes())
    os.utime(p, (1_760_000_000, 1_760_000_000))
    guess = resolve_captured_at(p.read_bytes(), p, timezone.utc)
    assert guess is not None
    assert guess.source == "mtime"
    assert guess.utc == datetime.fromtimestamp(1_760_000_000, timezone.utc)


def test_parse_offset_signs() -> None:
    assert parse_offset("+02:00") == timezone(timedelta(hours=2))
    assert parse_offset("-05:30") == timezone(timedelta(hours=-5, minutes=-30))
    assert parse_offset("junk") is None


def test_format_utc_shape() -> None:
    assert format_utc(datetime(2026, 10, 13, 14, 23, 55, 123456, tzinfo=timezone.utc)) == (
        "2026-10-13T14:23:55.123456Z"
    )
