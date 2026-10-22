"""Overlay rendering and the self-contained label-review page.

Pattern reused from ``scripts/build_gallery.py``: stdlib-only HTML with
the same dark palette. The page is written to ``output/labels_review``
together with copies of the overlay previews so a browser can load it
without the label store being reachable. The review server (plan Step
11, implemented in ``scripts/review_labels.py``) appends human verdicts
to ``decisions.jsonl``; this module never touches it.
"""

from __future__ import annotations

import html
import shutil
from pathlib import Path
from typing import Any

import cv2
import numpy as np

OVERLAY_WIDTH: int = 640
"""Preview width of rendered overlay previews in pixels."""

REJECT_REASONS: tuple[str, ...] = (
    "not_a_plant",
    "partial_plant",
    "includes_background",
    "multiple_plants",
    "wrong_object",
)
"""The five fixed reject reasons (plan Section 4.3)."""

CSS: str = (
    "body{font-family:system-ui,sans-serif;margin:24px;background:#111;"
    "color:#eee}"
    "h1{font-size:1.2rem}h2{font-size:1rem;font-weight:normal;color:#aaa}"
    ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,"
    "1fr));gap:16px}"
    ".card{background:#1b1b1b;border-radius:8px;overflow:hidden}"
    ".card img{width:100%;height:auto;display:block}"
    ".card .meta{padding:8px 12px;font-size:0.8rem;line-height:1.5;"
    "word-break:break-all}"
    ".card[data-state=accept]{outline:2px solid #3fb950}"
    ".card[data-state=reject]{outline:2px solid #f85149}"
    ".card[data-state=pending]{outline:2px solid transparent}"
    "button{background:#2b5797;color:#eee;border:0;border-radius:4px;"
    "padding:4px 10px;cursor:pointer}"
    "button:disabled{opacity:0.4;cursor:default}"
    "select{background:#111;color:#eee;border:1px solid #444;border-radius:4px}"
    "button:focus,select:focus{outline:2px solid #58a6ff}"
    "#counter{font-variant-numeric:tabular-nums}"
)


def render_overlay(
    image_bgr: np.ndarray,
    mask: np.ndarray,
    width: int = OVERLAY_WIDTH,
    alpha: float = 0.35,
) -> np.ndarray:
    """Blend a binary mask onto its frame at a fixed preview width.

    Args:
        image_bgr: BGR uint8 frame.
        mask: Binary mask with the same ``H x W`` as the frame.
        width: Target preview width (height keeps the aspect ratio).
        alpha: Mask blend weight in ``[0, 1]``.

    Returns:
        ``(h, width, 3)`` uint8 preview with the mask filled in green
        ``(80, 200, 80)`` BGR plus ``(0, 255, 0)`` contours.
    """
    height, img_width = image_bgr.shape[:2]
    out_height = int(round(height * width / img_width))
    img = cv2.resize(image_bgr, (width, out_height), interpolation=cv2.INTER_AREA)
    m = cv2.resize(
        mask, (width, out_height), interpolation=cv2.INTER_NEAREST
    )
    out = img.copy()
    tint = np.array([80, 200, 80], dtype=np.float64)
    out[m > 0] = (
        (1.0 - alpha) * img[m > 0].astype(np.float64) + alpha * tint
    ).astype(np.uint8)
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        cv2.drawContours(out, contours, -1, (0, 255, 0), 2)
    return out


def build_card(proposal: dict[str, Any], state: str) -> str:
    """Build one review card's HTML for a proposal.

    Args:
        proposal: Proposal record with ``sha256``, ``score``,
            ``area_fraction``, ``captured_at``.
        state: ``"accept"``, ``"reject"`` or ``"pending"``; anything other
            than pending renders the controls disabled.

    Returns:
        HTML fragment (all interpolated strings escaped).
    """
    sha = html.escape(str(proposal["sha256"]))
    decided = state != "pending"
    disabled = " disabled" if decided else ""
    captured_at = html.escape(str(proposal.get("captured_at", "")))
    score = float(proposal["score"])
    area_pct = float(proposal.get("area_fraction", 0.0)) * 100.0
    options = "".join(
        f'<option value="{html.escape(r)}">{html.escape(r)}</option>'
        for r in REJECT_REASONS
    )
    return (
        f'<div class="card" data-sha="{sha}" data-state="{html.escape(state)}">\n'
        f'<img src="overlays/{sha}.jpg" alt="{sha}">\n'
        f'<div class="meta">\n'
        f"<div>{captured_at} &middot; {sha[:12]} &middot; "
        f"score={score:.3f} &middot; area={area_pct:.1f}%</div>\n"
        f'<select class="reason">'
        + options
        + "</select>\n"
        f'<button class="accept" onclick="decide(this,\'{sha}\','
        f'\'accept\')"{disabled}>Accept</button>\n'
        f'<button class="reject" onclick="decide(this,\'{sha}\','
        f'\'reject\')"{disabled}>Reject</button>\n'
        f"</div>\n</div>\n"
    )


_JAVASCRIPT: str = """
function reasonFor(sha) {
  const card = document.querySelector('div.card[data-sha="' + sha + '"]');
  const sel = card && card.querySelector('select.reason');
  return sel ? sel.value : '';
}
async function decide(btn, sha, verdict) {
  const body = JSON.stringify({sha256: sha, verdict: verdict,
                               reason: reasonFor(sha)});
  try {
    const res = await fetch('/api/decision', {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: body});
    if (!res.ok) { alert('decision failed: ' + res.status); return; }
    const card = btn.closest('div.card');
    if (card) {
      card.dataset.state = verdict;
      const b = card.querySelectorAll('button');
      b.forEach(function (x) { x.disabled = true; });
      updateCounter();
    }
  } catch (err) {
    alert('decision failed: ' + err);
  }
}
let cardIndex = 0;
function focusCard(i) {
  const cards = document.querySelectorAll('div.card');
  if (!cards.length) return;
  cardIndex = Math.min(Math.max(i, 0), cards.length - 1);
  cards[cardIndex].querySelector('button').focus();
}
function updateCounter() {
  const cards = document.querySelectorAll('div.card');
  let pending = 0;
  cards.forEach(function (c) {
    if (c.dataset.state === 'pending') pending += 1;
  });
  document.getElementById('counter').textContent =
    pending + '/' + cards.length + ' pending';
}
document.addEventListener('keydown', function (ev) {
  if (ev.key === 'j') { focusCard(cardIndex + 1); ev.preventDefault(); }
  else if (ev.key === 'k') { focusCard(cardIndex - 1); ev.preventDefault(); }
  else if (ev.key === 'a') {
    const card = document.querySelectorAll('div.card')[cardIndex];
    if (card) {
      const sha = card.dataset.sha;
      decide(card.querySelector('button.accept'), sha, 'accept');
      ev.preventDefault();
    }
  } else if (ev.key === 'r') {
    const card = document.querySelectorAll('div.card')[cardIndex];
    if (card) {
      const sha = card.dataset.sha;
      decide(card.querySelector('button.reject'), sha, 'reject');
      ev.preventDefault();
    }
  }
});
"""


def build_review_site(
    proposals: list[dict[str, Any]],
    decisions: dict[str, dict[str, Any]],
    labels_root: Path,
    site_dir: Path,
    title: str = "PlantVision - SAM2 label review",
) -> Path:
    """Write the self-contained review page + copied overlay previews.

    Args:
        proposals: Proposal records (deduplicated by sha256 upstream).
        decisions: Mapping sha256 -> decision record (latest wins).
        labels_root: Label store containing ``overlays/<sha256>.jpg``.
        site_dir: Destination directory (parents created).
        title: ``<h1>`` text of the page.

    Returns:
        The written ``index.html`` path.

    Raises:
        RuntimeError: If an overlay preview file is missing.
        OSError: If ``site_dir`` is not writable (propagated).
    """
    overlay_src = labels_root / "overlays"
    site_overlays = site_dir / "overlays"
    site_overlays.mkdir(parents=True, exist_ok=True)
    for proposal in proposals:
        sha = str(proposal["sha256"])
        src = overlay_src / f"{sha}.jpg"
        if not src.exists():
            raise RuntimeError(f"missing overlay: {src}")
        shutil.copy2(src, site_overlays / f"{sha}.jpg")
    ordered = sorted(
        proposals,
        key=lambda p: (
            str(decisions.get(str(p["sha256"]), {}).get("verdict", "pending"))
            != "pending",
            float(p.get("score", 0.0)),
            str(p["sha256"]),
        ),
    )
    pending = sum(
        1
        for p in proposals
        if str(decisions.get(str(p["sha256"]), {}).get("verdict", "pending"))
        == "pending"
    )
    cards = "\n".join(
        build_card(
            p,
            str(decisions.get(str(p["sha256"]), {}).get("verdict", "pending")),
        )
        for p in ordered
    )
    doc = (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        f"<title>{html.escape(title)}</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n"
        f"<h1>{html.escape(title)}</h1>\n"
        f"<p>aria-live counter: <span id=\"counter\" "
        f"aria-live=\"polite\">{pending}/{len(proposals)} pending</span></p>\n"
        "<div class=\"grid\">\n"
        f"{cards}\n"
        "</div>\n"
        "<p>Keyboard: j/k next/previous card, a accept focused card, "
        "r reject focused card with the selected reason.</p>\n"
        "<p>decisions are only stored when served by "
        "scripts/review_labels.py</p>\n"
        f"<script>{_JAVASCRIPT}</script>\n"
        "</body>\n</html>\n"
    )
    (site_dir / "index.html").write_text(doc, encoding="utf-8")
    return site_dir / "index.html"
