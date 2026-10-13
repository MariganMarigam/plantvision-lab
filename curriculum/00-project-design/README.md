# Stage 00 — Project Design (lesson notes)

Stage 00 is the "decide before you build" stage: everything that would otherwise be
invented mid-code is written down, committed, and linked before a single line of
pipeline code exists.

## What this stage establishes

1. **Goal and spine** — one paragraph of intent (README.md): a phone photographs a
   lettuce plant every 10 minutes; an Ubuntu server pulls, deduplicates, stores, and
   measures; the output is a growth curve.
2. **Architecture** (docs/architecture.md): five components — phone (IP Webcam) →
   loader → ingest (sha256 gatekeeper) → filesystem + SQLite → CV pipeline →
   history/UI — with one responsibility each.
3. **Data contract** (docs/data-contract.md): the 7 observation fields, the
   `captured_at` (device clock) vs `received_at` (server clock) split, sha256
   idempotency (identical bytes are a no-op), and the 4 storage entities.
4. **ADR 0001** (docs/decisions/0001-data-flow.md): pull-not-push; 10-minute cadence;
   server-side scheduler; filesystem + SQLite; light-window gating (D8).
5. **Photoperiod** (configs/capture.yaml): light window 06:00–22:00 farm-local
   (start inclusive, end exclusive); `dark_policy: skip` — no capture in the dark,
   and a dark-window run is not a gap.
6. **Uncertainty journal** (docs/open-questions.md): five resolved open questions
   (OQ1–OQ5) plus the standing uncertainty list, append-only.
7. **Storage schema** (src/plantvision/storage/schema.sql): the 4 tables with
   indexes and WAL, applied with `IF NOT EXISTS`.

## Why this order

- Decisions deferred to coding time are decisions made twice — and worse.
- The repo is the lab notebook: gates, criteria, and evidence live next to the code
  they govern (ROADMAP.md stage acceptance).
- A public repo from day one keeps docs boring: no secrets, no embarrassment to scrub.

## Gate

Stage 00 exits when the acceptance criteria in ROADMAP.md §Stage 00 all hold
(repo visible, contract/diagram/ADR present, 6 labeled issues, uncertainties linked).
