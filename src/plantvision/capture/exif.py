"""Zero-dependency EXIF reader: DateTimeOriginal + OffsetTimeOriginal from JPEG bytes.

Pure function over bytes. Reads the APP1/EXIF segment, parses the TIFF block
(little- or big-endian) and extracts tag 0x9003 (``DateTimeOriginal``) and tag
0x9011 (``OffsetTimeOriginal``). Every failure mode — no EXIF, malformed
segments, garbage TIFF, implausible dates — collapses to ``None``; the reader
NEVER raises for any input.
"""

import struct
from datetime import datetime

_EXIF_PREFIX = b"Exif\x00\x00"


def _find_exif_tiff(data: bytes) -> bytes | None:
    """Walk JPEG segments and return the TIFF block of the first APP1/EXIF."""
    if len(data) < 12 or data[0:2] != b"\xff\xd8":
        return None
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            return None  # desynchronised segment walk
        marker = data[pos + 1]
        if marker == 0xDA:  # SOS: entropy data begins, no APP1 will follow
            return None
        if marker == 0x01 or 0xD0 <= marker <= 0xD9:
            pos += 2
            continue
        seg_len = int.from_bytes(data[pos + 2 : pos + 4], "big")
        if seg_len < 2:
            return None
        end = pos + 2 + seg_len
        if end > len(data):
            return None
        if marker == 0xE1 and data[pos + 4 : end][:6] == _EXIF_PREFIX:
            return data[pos + 10 : end]  # the TIFF block (4 + 6 header bytes)
        pos = end
    return None


def _ifd_entries(tiff: bytes, offset: int, endian: str) -> dict[int, str | int]:
    """Parse the IFD entries at ``offset`` into a ``tag -> raw value`` dict."""
    out: dict[int, str | int] = {}
    if offset + 2 > len(tiff):
        return out
    count = int.from_bytes(tiff[offset : offset + 2], endian)
    for i in range(count):
        base = offset + 2 + 12 * i
        if base + 12 > len(tiff):
            break
        tag = int.from_bytes(tiff[base : base + 2], endian)
        typ = int.from_bytes(tiff[base + 2 : base + 4], endian)
        cnt = int.from_bytes(tiff[base + 4 : base + 8], endian)
        raw = tiff[base + 8 : base + 12]
        if typ == 2:  # ASCII
            if cnt <= 4:
                value = raw[:cnt]
            else:
                ptr = int.from_bytes(raw, endian)
                if ptr + cnt > len(tiff):
                    continue
                value = tiff[ptr : ptr + cnt]
        elif typ in (3, 4):  # SHORT / LONG
            value = int.from_bytes(raw[:2] if typ == 3 else raw, endian)
        else:
            continue
        out[tag] = value
    return out


def _parse_tiff(tiff: bytes) -> dict[int, str | int]:
    """Parse a TIFF block into a tag -> raw-value dict (IFD0 + Exif SubIFD)."""
    if tiff[:2] == b"II":
        endian = "little"
    elif tiff[:2] == b"MM":
        endian = "big"
    else:
        return {}
    if int.from_bytes(tiff[2:4], endian) != 42:
        return {}
    out: dict[int, str | int] = {}
    out.update(_ifd_entries(tiff, int.from_bytes(tiff[4:8], endian), endian))
    ptr = out.get(0x8769)
    if isinstance(ptr, int) and ptr > 0:
        out.update(_ifd_entries(tiff, ptr, endian))  # Exif SubIFD
    return out


def read_exif_datetime(data: bytes) -> tuple[datetime, str] | None:
    """Extract ``(naive_datetime, offset_string)`` from JPEG EXIF bytes.

    Args:
        data: Raw JPEG bytes.

    Returns:
        ``(naive DateTimeOriginal text as datetime, OffsetTimeOriginal)`` where
        the offset is ``"+HH:MM"`` / ``"-HH:MM"``, or ``""`` when absent —
        or ``None`` whenever EXIF is absent, malformed or the date is
        implausible. Never raises.
    """
    try:
        tiff = _find_exif_tiff(data)
        if tiff is None:
            return None
        tags = _parse_tiff(tiff)
        raw = tags.get(0x9003)
        if not raw:
            return None
        text = (
            raw.decode("ascii", "replace").strip("\x00 ")
            if isinstance(raw, (bytes, bytearray))
            else str(raw).strip("\x00 ")
        )
        dt = datetime.strptime(text, "%Y:%m:%d %H:%M:%S")
        if not 2000 <= dt.year <= 2100:
            return None
        offset_raw = tags.get(0x9011, "")
        if isinstance(offset_raw, (bytes, bytearray)):
            offset = offset_raw.decode("ascii", "replace").strip("\x00 ")
        elif offset_raw:
            offset = str(offset_raw).strip("\x00 ")
        else:
            offset = ""
        return (dt, offset)
    except (IndexError, ValueError, TypeError, UnicodeDecodeError, struct.error):
        return None
