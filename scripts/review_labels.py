"""Review server: stdlib HTTP persistence of Accept/Reject decisions.

Serves the static review page built by ``plantvision.labeling.review``
and appends one JSONL line per human decision to
``data/labels/v1/decisions.jsonl`` (loopback only, last line wins).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Sequence

from plantvision.labeling.review import (
    build_review_site,
    build_card,  # noqa: F401  (re-exported convenience)
    render_overlay,  # noqa: F401
    REJECT_REASONS,
)
from plantvision.labeling.store import (
    append_jsonl,
    latest_decisions,
    read_jsonl,
)

_SHA_RE = re.compile(r"[0-9a-f]{64}")
_MAX_BODY_BYTES = 4096


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    p = argparse.ArgumentParser(description="Serve the label review page.")
    p.add_argument("--labels", default="data/labels/v1")
    p.add_argument("--site", default="output/labels_review")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--reviewer", default="local")
    p.add_argument(
        "--build-only",
        action="store_true",
        help="write the review page and exit (no server)",
    )
    return p.parse_args(argv)


def make_handler(
    site_dir: Path,
    decisions_path: Path,
    valid_shas: "set[str]",
    reviewer: str,
) -> "type[SimpleHTTPRequestHandler]":
    """Build a request handler class serving the page + POST decisions.

    Args:
        site_dir: Static directory served for GET requests.
        decisions_path: ``decisions.jsonl`` file to append verdicts to.
        valid_shas: Proposal sha256 values accepted by ``/api/decision``.
        reviewer: Reviewer identity stored on every decision.

    Returns:
        Handler class; wrap it in ``ThreadingHTTPServer`` to serve.
    """

    class ReviewHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(site_dir), **kwargs)

        def do_POST(self) -> None:  # noqa: N802 (http.server API)
            if self.path != "/api/decision":
                self.send_error(404)
                return
            length_header = self.headers.get("Content-Length")
            try:
                length = int(length_header) if length_header is not None else -1
            except ValueError:
                length = -1
            if length_header is None or not 0 <= length <= _MAX_BODY_BYTES:
                self.send_error(413)
                return
            body_bytes = self.rfile.read(length)
            try:
                body = json.loads(body_bytes.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self.send_error(400)
                return
            sha = body.get("sha256")
            if (
                not isinstance(sha, str)
                or _SHA_RE.fullmatch(sha) is None
                or sha not in valid_shas
            ):
                self.send_error(404)
                return
            verdict = body.get("verdict")
            if verdict not in ("accept", "reject"):
                self.send_error(400)
                return
            reason = body.get("reason")
            if verdict == "accept":
                reason = ""
            elif not isinstance(reason, str) or reason not in REJECT_REASONS:
                self.send_error(400)
                return
            record = {
                "sha256": sha,
                "verdict": verdict,
                "reason": reason,
                "reviewer": reviewer,
                "decided_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                append_jsonl(decisions_path, record)
            except OSError:
                self.send_error(500)
                return
            payload = json.dumps({"ok": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args) -> None:  # noqa: A002
            pass  # keep test output quiet

    return ReviewHandler


def serve(
    site_dir: Path,
    decisions_path: Path,
    valid_shas: "set[str]",
    reviewer: str,
    host: str,
    port: int,
) -> int:
    """Bind the loopback server with a small port fallback and serve.

    Args:
        site_dir: Directory containing the built review page.
        decisions_path: Destination of appended decisions.
        valid_shas: Proposal sha256 values; unknown POSTs get 404.
        reviewer: Reviewer identity stored on decisions.
        host: Bind host (loopback by default).
        port: Preferred port; ``port+1..port+3`` are tried as fallback.

    Returns:
        0 on clean Ctrl+C shutdown, 3 when all four ports are busy.
    """
    handler_cls = make_handler(site_dir, decisions_path, valid_shas, reviewer)
    server = None
    for candidate in (port, port + 1, port + 2, port + 3):
        try:
            server = ThreadingHTTPServer((host, candidate), handler_cls)
            break
        except OSError:
            continue
    if server is None:
        print("all ports busy")
        return 3
    print(f"serving http://{host}:{server.server_address[1]}/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point: build the page, then serve or exit."""
    args = parse_args(argv)
    labels = Path(args.labels)
    proposals = read_jsonl(labels / "proposals.jsonl")
    if not proposals:
        print("no proposals; run scripts/label_sam2.py first")
        return 2
    decisions = latest_decisions(read_jsonl(labels / "decisions.jsonl"))
    site = Path(args.site)
    page = build_review_site(
        proposals,
        decisions,
        labels,
        site,
        title="PlantVision - SAM2 label review",
    )
    if args.build_only:
        print(f"wrote {page}")
        return 0
    valid_shas = {str(p["sha256"]) for p in proposals}
    return serve(
        site,
        labels / "decisions.jsonl",
        valid_shas,
        args.reviewer,
        args.host,
        args.port,
    )


if __name__ == "__main__":
    sys.exit(main())
