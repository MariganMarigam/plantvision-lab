# PlantVision

Minimal phone-camera → Ubuntu → computer-vision pipeline for monitoring leafy-green
growth in a vertical farm at home. One phone, one shelf, one crop — and a system
small enough to actually run.

## Goal

A camera app on an Android phone photographs a lettuce plant every 10 minutes.
A tiny Ubuntu server pulls each frame, deduplicates it by content hash, files the
original on disk, and stores a row in SQLite. A CV pipeline measures the plant's
projected visible area and shape over time, turning raw frames into a growth
history you can query and plot.

The intent is not a smart-farm product. It is a working vertical slice: capture →
store → measure → history, kept deliberately minimal so it survives contact with
reality.

## System diagram

See [docs/architecture.md](docs/architecture.md) for the component breakdown and
the data-flow diagram (`docs/architecture.md#data-flow`).

## Minimal stack

| Concern | Choice | Rationale |
|---|---|---|
| Camera | Old Android phone running [IP Webcam](https://github.com/TheOriginalGently/IP-Webcam), fixed mount | Free, no custom Android app; MJPEG/JPEG-over-HTTP is trivial to pull server-side |
| Transport | Wi-Fi pull: server polls `http://<phone-ip>:8080/photo.jpg` every 10 min | Pull model means no Android background-task scheduling to fight; phone needs only power + fixed IP |
| Server | Ubuntu box (this PC), Python 3.12 | Where the data lives anyway; apt-installed OS deps |
| Storage | Filesystem for originals (`data/originals/`), SQLite for metadata and measurements | Files for bytes, database for structure; SQLite is zero-ops and one `schema.sql` |
| Idempotency | `sha256` of raw image bytes | Re-sent frames produce no duplicate rows |
| CV | OpenCV; classical segmentation first (RGB/HSV thresholds, morphology) | No model training before there is labeled data to train on |
| Scale reference | Printed ArUco marker (`DICT_4X4_50`, 50 mm) beside the plant | In-frame metric scale; OpenCV-native detections |
| Photoperiod | Capture only during the light window (06:00–22:00); dark frames skipped | RGB frames taken in darkness cannot support growth metrics |
| UI/plotting | Matplotlib notebooks → (Stage 5+) a small dashboard | History first, dashboards later |

## Repo layout

```
plantvision-lab/
├── README.md            # this file
├── ROADMAP.md           # stages 00–08 with acceptance criteria
├── pyproject.toml       # packaging + dependencies
├── configs/
│   ├── capture.yaml     # camera, interval, retry, photoperiod
│   └── pipeline.yaml    # ROI, scale reference, metrics
├── docs/
│   ├── architecture.md  # components + data-flow diagram
│   ├── data-contract.md # field/entity contract for all stored data
│   ├── glossary.md      # CV + plant-tracking terms
│   ├── decisions/       # architecture decision records
│   └── open-questions.md# uncertainty journal
├── src/plantvision/
│   ├── api/           # (Stage 5) HTTP API
│   ├── ingest/        # (Stage 1+) capture + ingest logic
│   ├── storage/       # schema.sql + DB helpers
│   ├── vision/        # (Stage 3) segmentation + measurement
│   └── analytics/     # (Stage 4) growth curves, summaries
├── tests/               # pytest
├── data/                # runtime data (gitignored; see data/README.md)
├── curriculum/          # per-stage lesson notes
└── experiments/         # scratch notebooks and trials
```

## Quickstart

> Placeholder — filled in at Stage 1 when the ingest loop exists.
> Until then: create the venv with `.venv/bin/python -m venv .venv`,
> apply the schema with
> `sqlite3 plantvision.db < src/plantvision/storage/schema.sql`,
> and read [ROADMAP.md](ROADMAP.md) to see what comes next.

## Documentation map

- [ROADMAP.md](ROADMAP.md) — the full stage 00–08 plan with acceptance criteria.
- [docs/open-questions.md](docs/open-questions.md) — resolved and open uncertainties,
  tracked append-only.
- [docs/data-contract.md](docs/data-contract.md) — the contract every ingest/processing
  component must honor.
- [docs/decisions/](docs/decisions/) — architecture decision records.
- [docs/connect-phone.md](docs/connect-phone.md) — turn an Android phone into the
  IP-Webcam camera the capture stand pulls frames from.

## License

No license selected yet; all rights reserved.
