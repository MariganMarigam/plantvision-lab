"""HTTP pull client for the IP Webcam snapshot endpoint (stdlib urllib only)."""

import socket
import urllib.error
import urllib.request
from urllib.request import urlopen


class CaptureError(Exception):
    """Raised when a photo cannot be pulled from the camera endpoint."""


def fetch_photo(url: str, timeout_s: float = 10.0) -> bytes:
    """Fetch one JPEG snapshot from the camera endpoint.

    Args:
        url: Snapshot URL (e.g. "http://<phone-ip>:8080/photo.jpg").
        timeout_s: Per-attempt HTTP timeout in seconds.

    Returns:
        Raw JPEG bytes (the body starts with the JPEG SOI marker b"\\xff\\xd8").

    Raises:
        CaptureError: On urllib errors (DNS/connection/HTTP/timeout) with the
            underlying message, on a non-200 status, or on a non-JPEG body.
            Never returns empty bytes.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "plantvision/0.1"})
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            status = resp.status
            body = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, socket.timeout) as exc:
        raise CaptureError(str(exc)) from exc
    if status != 200:
        raise CaptureError(f"HTTP {status}")
    if not body.startswith(b"\xff\xd8"):
        raise CaptureError("not a JPEG")
    return body
