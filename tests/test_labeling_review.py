"""Overlay rendering + review page + review server (plan Steps 6 + 11)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

from plantvision.labeling.review import (
    REJECT_REASONS,
    build_card,
    build_review_site,
    render_overlay,
)


def _load_script():
    """Load scripts/review_labels.py without package machinery."""
    import importlib.util

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "review_labels", root / "scripts" / "review_labels.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


make_handler = _load_script().make_handler

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _proposal(sha: str, score: float, captured_at: str = "2026-10-16T09:00:00+00:00") -> dict:
    return {
        "sha256": sha,
        "score": score,
        "area_fraction": 0.1,
        "frame_relpath": f"cam/zone/2026-10-16/{sha[:8]}.jpg",
        "mask_relpath": f"masks/{sha}.png",
        "captured_at": captured_at,
    }


def _overlay_fixture(labels_root: Path, shas: list[str]) -> None:
    overlay_dir = labels_root / "overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    img = np.zeros((10, 20, 3), dtype=np.uint8)
    for sha in shas:
        assert cv2.imwrite(str(overlay_dir / f"{sha}.jpg"), img)


def test_render_overlay_shape_and_dtype() -> None:
    img = np.zeros((50, 100, 3), dtype=np.uint8)
    mask = np.zeros((50, 100), dtype=np.uint8)
    mask[10:30, 20:80] = 255
    out = render_overlay(img, mask, width=640)
    # h = round(H * width / W) = round(50 * 640 / 100) = 320
    assert out.dtype == np.uint8
    assert out.shape == (320, 640, 3)
    # fill blend differs from source pixels where mask > 0
    assert (out[100, 300] != 0).any()   # maps to original (15, 47): inside mask
    assert (out[10, 50] == 0).all()     # maps to original (1, 7): outside mask


def test_site_contains_one_card_per_proposal(tmp_path: Path) -> None:
    labels_root = tmp_path / "labels"
    _overlay_fixture(labels_root, [SHA_A, SHA_B])
    site = tmp_path / "site"
    proposals = [_proposal(SHA_A, 0.9), _proposal(SHA_B, 0.3)]
    page = build_review_site(proposals, {}, labels_root, site)
    assert page == site / "index.html"
    html = page.read_text(encoding="utf-8")
    assert html.count('class="card"') == 2
    assert 'data-sha="' + SHA_A + '"' in html
    for reason in REJECT_REASONS:
        assert reason in html
    assert "/api/decision" in html
    assert "aria-live" in html
    assert "2/2 pending" in html  # both proposals pending


def test_site_copies_overlays_and_is_self_contained(tmp_path: Path) -> None:
    labels_root = tmp_path / "labels"
    _overlay_fixture(labels_root, [SHA_A])
    site = tmp_path / "site"
    build_review_site([_proposal(SHA_A, 0.9)], {}, labels_root, site)
    assert (site / "overlays" / f"{SHA_A}.jpg").exists()
    html = (site / "index.html").read_text(encoding="utf-8")
    assert f'src="overlays/{SHA_A}.jpg"' in html


def test_site_marks_decided_cards_disabled(tmp_path: Path) -> None:
    labels_root = tmp_path / "labels"
    _overlay_fixture(labels_root, [SHA_A])
    site = tmp_path / "site"
    decisions = {
        SHA_A: {"verdict": "accept", "reason": "", "reviewer": "local",
                "decided_at": "2026-10-17T10:05:00+00:00"},
    }
    html = build_review_site(
        [_proposal(SHA_A, 0.9)], decisions, labels_root, site
    ).read_text(encoding="utf-8")
    assert f'data-sha="{SHA_A}"' in html
    assert 'data-state="accept"' in html
    assert "disabled" in html


def test_site_orders_pending_low_confidence_first(tmp_path: Path) -> None:
    labels_root = tmp_path / "labels"
    _overlay_fixture(labels_root, [SHA_A, SHA_B, SHA_C])
    site = tmp_path / "site"
    proposals = [_proposal(SHA_C, 0.7), _proposal(SHA_A, 0.9), _proposal(SHA_B, 0.3)]
    decisions = {SHA_C: {"verdict": "accept", "reason": "", "reviewer": "l",
                         "decided_at": "x"}}
    html = build_review_site(
        proposals, decisions, labels_root, site
    ).read_text(encoding="utf-8")
    pos_b = html.index('data-sha="' + SHA_B + '"')  # pending, lowest score
    pos_a = html.index('data-sha="' + SHA_A + '"')  # pending, higher score
    pos_c = html.index('data-sha="' + SHA_C + '"')  # decided, last
    assert pos_b < pos_a < pos_c


def test_build_card_includes_buttons_and_state() -> None:
    card = build_card(_proposal(SHA_A, 0.9), "pending")
    assert 'data-state="pending"' in card
    assert ">Accept</button>" in card
    assert ">Reject</button>" in card
    decided = build_card(_proposal(SHA_A, 0.9), "reject")
    assert 'data-state="reject"' in decided
    assert decided.count("disabled") >= 2


def test_post_decision_appends_jsonl(tmp_path: Path) -> None:
    labels_root = tmp_path / "labels"
    _overlay_fixture(labels_root, [SHA_A])
    site = tmp_path / "site"
    build_review_site([_proposal(SHA_A, 0.9)], {}, labels_root, site)
    decisions_path = labels_root / "decisions.jsonl"
    handler_cls = make_handler(site, decisions_path, {SHA_A}, "local")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps({"sha256": SHA_A, "verdict": "accept",
                              "reason": ""}).encode()
        url = f"http://127.0.0.1:{server.server_address[1]}/api/decision"
        req = urllib.request.Request(url, data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            assert json.loads(resp.read()) == {"ok": True}
    finally:
        server.shutdown()
        server.server_close()
    lines = [json.loads(l) for l in decisions_path.read_text().splitlines() if l]
    assert len(lines) == 1
    assert lines[0]["sha256"] == SHA_A
    assert lines[0]["verdict"] == "accept"
    assert lines[0]["reason"] == ""
    assert lines[0]["reviewer"] == "local"
    assert lines[0]["decided_at"]


def _server(tmp_path: Path, shas: list[str]):
    site = tmp_path / "site"
    handler_cls = make_handler(
        site, tmp_path / "decisions.jsonl", set(shas), "local"
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/decision"
    return server, url


def _post(url: str, payload: bytes):
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_post_rejects_unknown_sha(tmp_path: Path) -> None:
    server, url = _server(tmp_path, {SHA_A})
    try:
        bad_format = json.dumps({"sha256": "zz", "verdict": "accept",
                                 "reason": ""}).encode()
        unknown = json.dumps({"sha256": "f" * 64, "verdict": "accept",
                              "reason": ""}).encode()
        assert _post(url, bad_format) == 404
        assert _post(url, unknown) == 404
        assert _post(url, b"{not json") == 400
        assert _post(url, json.dumps({"sha256": SHA_A, "verdict": "maybe",
                                      "reason": ""}).encode()) == 400
        assert _post(url, json.dumps({"sha256": SHA_A, "verdict": "reject",
                                      "reason": "nonsense"}).encode()) == 400
    finally:
        server.shutdown()
        server.server_close()
    assert not (tmp_path / "decisions.jsonl").exists()


def test_post_rejects_bad_verdict(tmp_path: Path) -> None:
    server, url = _server(tmp_path, {SHA_A})
    try:
        # missing verdict -> 400; missing reason on reject -> 400
        no_verdict = json.dumps({"sha256": SHA_A}).encode()
        bad_reason = json.dumps({"sha256": SHA_A, "verdict": "reject",
                                 "reason": "nonsense"}).encode()
        assert _post(url, no_verdict) == 400
        assert _post(url, bad_reason) == 400
    finally:
        server.shutdown()
        server.server_close()


def test_post_rejects_oversized_body(tmp_path: Path) -> None:
    server, url = _server(tmp_path, {SHA_A})
    try:
        big = json.dumps({"sha256": SHA_A, "verdict": "accept", "reason": "",
                          "pad": "x" * 5000}).encode()
        assert _post(url, big) == 413
    finally:
        server.shutdown()
        server.server_close()
