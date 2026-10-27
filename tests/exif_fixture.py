"""Synthetic JPEG+EXIF builders for tests. No third-party dependency."""

import struct
from fractions import Fraction

import cv2
import numpy as np

_IFD0_OFF = 8
_EXIF_OFF = 26
_DT_BYTES = 20
_OT_BYTES = 7


def jpeg_bytes(bgr: np.ndarray | None = None) -> bytes:
    """A real, decodable JPEG (default: mid-grey 64x64)."""
    img = np.full((64, 64, 3), 128, np.uint8) if bgr is None else bgr
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _tiff(
    dt_str: str,
    offset_str: str | None,
    endian: str = "<",
    exposure_s: float | None = None,
    white_balance: int | None = None,
    iso: int | None = None,
) -> bytes:
    """TIFF block: IFD0 -> ExifIFD with datetime and optional camera settings."""
    prefix = b"II" if endian == "<" else b"MM"
    n_tags = (
        1
        + int(offset_str is not None)
        + int(exposure_s is not None)
        + int(white_balance is not None)
        + int(iso is not None)
    )
    data_start = _EXIF_OFF + 2 + 12 * n_tags + 4
    data = bytearray()
    final_tags: list[bytes] = []

    dt_off = data_start
    final_tags.append(struct.pack(endian + "HHII", 0x9003, 2, _DT_BYTES, dt_off))
    data += dt_str.encode("ascii").ljust(_DT_BYTES, b"\x00")

    if offset_str:
        ot_off = data_start + len(data)
        final_tags.append(struct.pack(endian + "HHII", 0x9011, 2, _OT_BYTES, ot_off))
        data += offset_str.encode("ascii").ljust(_OT_BYTES, b"\x00")

    if exposure_s is not None:
        fraction = Fraction(exposure_s).limit_denominator(100_000)
        exp_off = data_start + len(data)
        final_tags.append(struct.pack(endian + "HHII", 0x829A, 5, 1, exp_off))
        data += struct.pack(endian + "II", fraction.numerator, fraction.denominator)

    if white_balance is not None:
        final_tags.append(struct.pack(endian + "HHI", 0xA403, 3, 1)
                          + struct.pack(endian + "H", white_balance) + b"\x00\x00")

    if iso is not None:
        final_tags.append(struct.pack(endian + "HHI", 0x8827, 3, 1)
                          + struct.pack(endian + "H", iso) + b"\x00\x00")

    body = bytearray()
    body += prefix + struct.pack(endian + "HI", 42, _IFD0_OFF)
    body += struct.pack(endian + "H", 1)                            # IFD0 count
    body += struct.pack(endian + "HHII", 0x8769, 4, 1, _EXIF_OFF)   # Exif pointer
    body += struct.pack(endian + "I", 0)                            # next IFD0
    assert len(body) == _EXIF_OFF
    body += struct.pack(endian + "H", len(final_tags))
    for tag_bytes in final_tags:
        body += tag_bytes
    body += struct.pack(endian + "I", 0)
    assert len(body) == data_start, (len(body), data_start)
    body += data
    return bytes(body)


def jpeg_with_exif(
    dt_str: str = "2026:10:13 14:23:55",
    offset_str: str | None = "+00:00",
    endian: str = "<",
    bgr: np.ndarray | None = None,
    exposure_s: float | None = None,
    white_balance: int | None = None,
    iso: int | None = None,
) -> bytes:
    """JPEG with an inserted APP1/EXIF segment right after SOI."""
    tiff = _tiff(dt_str, offset_str, endian, exposure_s, white_balance, iso)
    app1 = b"\xff\xe1" + struct.pack(">H", 2 + 6 + len(tiff)) + b"Exif\x00\x00" + tiff
    jpg = jpeg_bytes(bgr)
    return jpg[:2] + app1 + jpg[2:]
