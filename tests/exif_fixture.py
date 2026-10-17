"""Synthetic JPEG+EXIF builders for tests. No third-party dependency."""

import struct

import cv2
import numpy as np

_IFD0_OFF = 8
_EXIF_OFF = 26
_DT_OFF = 56
_OT_OFF = 76


def jpeg_bytes(bgr: np.ndarray | None = None) -> bytes:
    """A real, decodable JPEG (default: mid-grey 64x64)."""
    img = np.full((64, 64, 3), 128, np.uint8) if bgr is None else bgr
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _tiff(dt_str: str, offset_str: str | None, endian: str = "<") -> bytes:
    """TIFF block: IFD0 -> ExifIFD -> DateTimeOriginal (+ OffsetTimeOriginal)."""
    prefix = b"II" if endian == "<" else b"MM"
    body = bytearray()
    body += prefix + struct.pack(endian + "HI", 42, _IFD0_OFF)   # 0..8
    body += struct.pack(endian + "H", 1)                          # IFD0 count -> 10
    body += struct.pack(endian + "HHII", 0x8769, 4, 1, _EXIF_OFF)  # -> 22
    body += struct.pack(endian + "I", 0)                          # next IFD -> 26
    body += struct.pack(endian + "H", 2 if offset_str else 1)     # ExifIFD count
    body += struct.pack(endian + "HHII", 0x9003, 2, 20, _DT_OFF)
    if offset_str:
        body += struct.pack(endian + "HHII", 0x9011, 2, 7, _OT_OFF)
    body += struct.pack(endian + "I", 0)                          # next IFD
    body += b"\x00" * (_DT_OFF - len(body))                       # pad to DT area
    body += dt_str.encode("ascii").ljust(20, b"\x00")             # 56..76, 20 bytes incl NUL
    if offset_str:
        body += offset_str.encode("ascii").ljust(7, b"\x00")      # 76..83, 7 bytes incl NUL
    return bytes(body)


def jpeg_with_exif(dt_str: str = "2026:10:13 14:23:55", offset_str: str | None = "+00:00",
                   endian: str = "<", bgr: np.ndarray | None = None) -> bytes:
    """JPEG with an inserted APP1/EXIF segment right after SOI."""
    tiff = _tiff(dt_str, offset_str, endian)
    app1 = b"\xff\xe1" + struct.pack(">H", 2 + 6 + len(tiff)) + b"Exif\x00\x00" + tiff
    jpg = jpeg_bytes(bgr)
    return jpg[:2] + app1 + jpg[2:]
