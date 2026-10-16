# 02 — Capture setup: fixed rig, cadence, and protocol

Physical + operational protocol for the Stage-2 capture stand, plus how to
read the capture log. Code side: `src/plantvision/capture/`, config side:
`configs/capture.yaml`, scheduler side: `../deploy/`.

## 1. Mount procedure (fixed rig)

- Mount the phone so the whole tray + plant are framed identically every time:
  same distance, same angle, same zoom (lock zoom to 1x in IP Webcam if
  available). Any re-mount invalidates before/after comparisons.
- Power the phone continuously (USB charger) — a phone that dies at night
  leaves a gap in the growth curve.
- Keep the phone on the same Wi-Fi (LAN) 24/7; PC pulls one frame from
  `http://<phone-ip>:8080/photo.jpg` (IP Webcam app; set `source_url` in
  `configs/capture.yaml` to the phone's real LAN address).
- Disable "sleep when idle" (keep screen on) in IP Webcam settings: Android
  cameras stop serving frames when the display sleeps; pulling does not wake
  the phone. This costs battery — hence the permanent charger.

## 2. In-frame scale reference: ArUco marker

- Print one ArUco marker from `DICT_5X5_50` at **45 mm** marker width.
- Place it flat (or standing) beside the plant so it is always inside the
  frame: it converts pixels → millimetres and anchors all later growth
  metrics (projected leaf area, crown shape).
- Handle the marker as a fixed reference: don't move it between sessions; if
  you must move it, re-mount the whole rig and note the session break.

## 3. Cadence: one frame every 10 minutes

- 10-minute cadence (144 frames/day inside the light window) is dense enough
  to see daily growth relative to leaf size and sparse enough to stay
  trivially storable and analyzable on a laptop.
- The trade-off: the phone must stay awake and serving for the whole
  photoperiod; a sleeping phone = missed frames. Cadence is owned by the
  systemd timer (`OnUnitActiveSec=10min`, `Persistent=true` backfills one
  missed run after reboot/sleep) — not by the capture code.

## 4. Reading `data/capture.log`

One JSONL line per capture run, in order:

```json
{"ts": "2026-10-13T18:00:00.123456Z", "status": "ok", "sha256": "...", "path": "data/originals/..."}
```

- `ok` — fresh frame stored. `duplicate` — identical bytes (same sha256) were
  already stored; no new file.
- `skipped_dark` — run happened outside `light_window`; nothing fetched. This
  is expected every night, not an error.
- `gap` — the capture failed after retries (phone offline, HTTP error). Gaps
  are never silent; each failure is logged with `error: "<message>"`.
  Detect gaps: `grep '"status": "gap"' data/capture.log` (or count `ok` lines
  per hour — fewer than 6 in an hour of daylight means missing frames).
- `spooled` — storage hiccup; the frame waits in `data/spool/` and is
  re-stored automatically on the next successful run.

## 5. Photoperiod rule (decision D8)

Captures run only inside `light_window` (default `06:00`–`22:00` farm-local
time; start inclusive, end exclusive). Runs in the dark window are *skipped*:
no frame is fetched, no gap is logged (`dark_policy: skip`). RGB frames taken
in darkness are unusable for growth metrics; night/spectral analysis with a
different camera is out of scope.
