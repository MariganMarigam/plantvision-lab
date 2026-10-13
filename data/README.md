# data/ — runtime data layout + retention policy

Everything under `data/` is **runtime data: it never enters Git** (`.gitignore` excludes
the subdirectories below; this README is the only tracked file here). Backups are a
variant of the same concern: do not backup into Git; back up the host.

## Layout

| Directory | Contents | Written by | In Git? |
|---|---|---|---|
| `data/originals/` | Raw JPEG frames exactly as pulled from the phone, named by `image_id`. **Never modified after write.** | ingest (Stage 02+) | no (gitignored) |
| `data/derived/` | Anything derived from originals: resized thumbnails, histograms, crops. | CV pipeline (Stage 05+) | no (gitignored) |
| `data/masks/` | Binary segmentation masks, 1:1 with processed frames. | CV pipeline (Stage 05+) | no (gitignored) |

Sub-paths are by capture date, e.g. `data/originals/2026/10/13/<image_id>.jpg`.

## Retention policy (MVP)

1. **Keep all originals during the MVP.** Deleting originals destroys the evidence the
   measurements were derived from and is not permitted at Stage 0–6; pruning rules are
   deferred until the pipeline is trusted (Stage 08+).
2. **Size envelope**: ≤ 1280×720 JPEG at ≤ 300 KB per frame → ≤ ~16 GB/year at the
   10-minute cadence. Check free space before Stage 02 starts.
3. **Weekly free-space check**: a scheduled (cron/systemd) check warns when free space on
   the data volume drops below a threshold; disk full must fail loudly, never silently
   corrupt the dataset.

## Backup note

`data/originals/` is irreplaceable (each moment of plant growth exists exactly once) —
the SQLite database, in contrast, is fully re-derivable from the originals plus the CV
pipeline (metadata and measurements are views over re-runnable computation). Backup the
originals directory to a second disk periodically if the shelf is long-running.

## Related decisions

- sha256 idempotency and `captured_at`/`received_at` semantics: `docs/data-contract.md`.
- Photon-necessity gating: dark-window frames are skipped entirely (`configs/capture.yaml`
  `dark_policy: skip`, decision D8).
