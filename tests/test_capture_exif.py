"""Unit tests for the hand-rolled EXIF DateTimeOriginal reader (Step 3)."""

from datetime import datetime

import pytest

from plantvision.capture.exif import read_exif_datetime
from tests.exif_fixture import jpeg_bytes, jpeg_with_exif


def test_reads_datetime_original_with_offset() -> None:
    assert read_exif_datetime(jpeg_with_exif("2026:10:13 14:23:55", "+02:00")) == (
        datetime(2026, 10, 13, 14, 23, 55),
        "+02:00",
    )


def test_reads_datetime_original_without_offset() -> None:
    result = read_exif_datetime(jpeg_with_exif("2026:10:13 14:23:55", None))
    assert result is not None
    assert result[1] == ""


@pytest.mark.parametrize("endian", ["<", ">"])
def test_big_endian_tiff(endian: str) -> None:
    result = read_exif_datetime(jpeg_with_exif("2026:10:13 14:23:55", "+00:00", endian=endian))
    assert result == (datetime(2026, 10, 13, 14, 23, 55), "+00:00")


def test_no_exif_returns_none() -> None:
    assert read_exif_datetime(jpeg_bytes()) is None


def test_truncated_app1_returns_none() -> None:
    assert read_exif_datetime(jpeg_with_exif()[:24]) is None


def test_non_jpeg_returns_none() -> None:
    assert read_exif_datetime(b"not-a-jpeg") is None


def test_invalid_datetime_string_returns_none() -> None:
    assert read_exif_datetime(jpeg_with_exif("0000:00:00 00:00:00")) is None


def test_out_of_range_year_returns_none() -> None:
    assert read_exif_datetime(jpeg_with_exif("1999:12:31 23:59:59")) is None
