# ADR 0001 — Data flow: pull from IP Webcam, 10-minute cadence, filesystem + SQLite

- **Status**: Accepted
- **Date**: 2026-10-13
- **Deciders**: project owner, with scout/ivan planning notes (Stage 0)

## Context

PlantVision is a one-camera, one-zone home vertical-farm monitor. The sensor is an Android
phone mounted over a single lettuce shelf, running a camera app; the compute is one Ubuntu
PC. Frames must arrive on a predictable 10-minute cadence, survive network hiccups and
machine restarts without duplicates or silent gaps, and stay usable for years of growth
curves (context notes: `reflection.md:124-158` — the wisdom/decision record;
`reflection.md:445-471` — the cadence discussion, both in the planning workspace).

Constraints that shaped the decision:

- No custom Android app is wanted (building/maintaining one is a project in itself);
  the phone must only run an existing, reliable camera server app.
- The phone is powered 24/7 on the same Wi-Fi SSID; the host PC is always-on.
- Home network (no port forwarding, no cloud ingest; minimal edge stack).
- Photoperiod (D8): the grow lights are off ~8 h/day; RGB frames taken in darkness are
  unusable for growth metrics, so capture must be gated to the light window.
- Storage must make re-delivery safe (idempotency) and keep raw bytes immutable on disk
  while keeping queryable metadata in a database.

## Decision

1. **Pull transport.** The phone runs the **IP Webcam** app; the Ubuntu server *pulls* a
   frame over HTTP (`http://<phone-ip>:8080/photo.jpg`). The scheduler lives on the server,
   not on the phone. Rationale: a pull client on the PC is trivial (stdlib HTTP), debuggable
   with curl, unaffected by Android doze/background restrictions, and needs no app upgrade
   — the phone is just a camera server.
2. **Cadence: every 10 minutes.** Enough temporal resolution for leafy-green growth
   (hour-scale changes dominate day-scale drift); low bandwidth and storage cost
   (≤ 300 KB JPEG → ≤ 16 GB/year at 1280×720).
3. **Server-side scheduler.** cron/systemd timer on Ubuntu triggers one capture attempt;
   the capture run logs planned vs received so gaps are never silent. The scheduler
   runs 24/7 but each run self-gates to the configured light window
   (`light_window: 06:00–22:00` local, `dark_policy: skip`): outside the window the run
   exits `skipped_dark` — no capture, and not counted as a gap.
4. **Storage: filesystem for originals + SQLite for structure.** Each accepted frame's raw
   bytes go to `data/originals/` (never modified after write, never in Git); metadata and
   measurements go to SQLite (`snapshot`, `processing`, `measurement`, `model_version`);
   idempotency by sha256 of the raw bytes (see
   [docs/data-contract.md](../data-contract.md), §3).

## Consequences

- **The phone must stay awake and powered** with battery optimisation disabled for IP
  Webcam; a phoneside sleep kills the pipeline silently at the source. Mitigation:
  keep it charging, keep the app in the foreground, verify liveness via fetch failures.
- **No Android development.**Pull-side retry/backoff lives entirely on the Ubuntu server
  (retry schedule in `configs/capture.yaml`).
- **SQLite is the single database.** Zero-ops and fits one-writer load; if multi-host
  access is ever needed, migration (e.g. to Postgres) is a later, separate decision —
  the data contract, not the DB engine, is the interface.
- **A 10-min cadence with 16 GB/yr means disk is cheap but not free**; retention follows
  [data/README.md](../../data/README.md) (keep-all for MVP + weekly free-space check).
- **Light-window gating is configuration, not code convention** — consumers must honor
  `configs/capture.yaml` (D8) rather than hard-code times.

## Alternatives considered

1. **Push from the phone (Open Camera + automation/rsync).** Rejected: relies on Android
   background execution and task automation working reliably for months; harder to
   observe and retry correctly server-side; still requires the server-side ingest logic
   we already need.
2. **Write our own Android app.** Rejected for Stage 0–6: months of work before the first
   growth curve; revisit only if IP Webcam proves unreliable.
3. **Streaming (MJPEG) capture instead of snapshots.** Rejected: continuous decode wastes
   power/CPU for a 10-min cadence; snapshot-on-demand is lighter and more deterministic.
4. **Postgres instead of SQLite.** Rejected at this scale: one writer, one host, zero admin
   burden preferred; revisit if Stage 07+ dashboards need concurrent writers.

## References

- `output/research/2026-10-13-phone-capture-minimal-stack.md` (planning workspace; tooling
  and pitfalls behind the pull choice).
- `output/state/plantvision.md` decisions **D2** (pull), **D3** (10 min), **D8** (photoperiod).
- `docs/data-contract.md` — field rules the flow must honor.
- `docs/architecture.md` — components and data-flow diagram.
