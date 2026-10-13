"""Tests for the IP-Webcam pull client (Stage 2 Task 2.2)."""

from plantvision.capture.pull import CaptureError, fetch_photo


class _FakeResponse:
    """Minimal urlopen() stand-in: context manager with .status and .read()."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_fetch_photo_ok(monkeypatch) -> None:
    body = b"\xff\xd8fake-jpeg-payload\xff\xd9"
    monkeypatch.setattr(
        "plantvision.capture.pull.urlopen",
        lambda req, timeout: _FakeResponse(200, body),
    )
    assert fetch_photo("http://example.invalid:8080/photo.jpg") == body


def test_fetch_photo_bad_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "plantvision.capture.pull.urlopen",
        lambda req, timeout: _FakeResponse(500, b"\xff\xd8x\xff\xd9"),
    )
    try:
        fetch_photo("http://example.invalid:8080/photo.jpg")
    except CaptureError:
        pass
    else:
        raise AssertionError("CaptureError not raised for HTTP 500")


def test_fetch_photo_not_jpeg(monkeypatch) -> None:
    monkeypatch.setattr(
        "plantvision.capture.pull.urlopen",
        lambda req, timeout: _FakeResponse(200, b"garbage"),
    )
    try:
        fetch_photo("http://example.invalid:8080/photo.jpg")
    except CaptureError:
        pass
    else:
        raise AssertionError("CaptureError not raised for non-JPEG body")
