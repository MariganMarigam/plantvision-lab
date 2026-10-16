# PlantVision — Roadmap (Stages 00–08)

> Author: scout · 2026-10-13.
> Sources of truth: `task/reflection.md` (plan spine), `task/plan_practic_CV.txt` (curriculum outline),
> `task/practic_CV.txt` (theory, cited by line), `output/research/2026-10-13-phone-capture-minimal-stack.md` (E1).
> Locked decisions **D1–D8** are recorded in `output/state/plantvision.md` (D8 = photoperiod).
> **Deployment:** cadence is now **10 minutes** (D3); Linux uses `deploy/systemd/` (dev host) and Windows uses `deploy/windows/` (running host) — see `deploy/windows/README.md`.

## How to read this roadmap
- Each stage ends with a **verifiable acceptance criterion** — you only advance after the check passes
  (`reflection.md:219`, `reflection.md:495`).
- **Estimation**: S < 30 LoC / 1 file · M 30–100 LoC / 1–3 files · L 100+ LoC / 3+ files (per `scout-artifacts`).
- **Theory map** cites `practic_CV.txt:<line>` (deepest component) and `reflection.md:<line>` (spine).
- Stages 00–02 are specified here; 03–08 are scoped lightly and expanded in their own stage plans.

## Stage summary

| Stage | Name | Deliverable | Deps | Est |
|-------|------|-------------|------|-----|
| 00 | Project design & GitHub | public repo + docs + first issues | — (needs G1) | M |
| 01 | Image lab | reproducible single-image analysis in a notebook | 00 | S |
| 02 | Capture stand & protocol | fixed rig, comparable test series, 10-min capture | 01 | M |
| 03 | Ingestion & durable storage | idempotent HTTP ingest, originals + metadata | 02 | M |
| 04 | Automated 10-min capture | scheduled pull, gap/error logging | 03 | M |
| 05 | First growth measurer (no NN) | classic-OpenCV mask + projected-area metric + plot | 04 | L |
| 06 | Dataset & model choice | labelled set + fine-tuned segmentation vs baseline | 05 | L |
| 07 | Temporal analysis & UI | metrics time-series, growth charts, read-only dashboard | 06 | L |
| 08 | Prototype validation & farm prep | accuracy/gap limits known, expansion rules | 07 | L |

---

## Stage 00 — Project design & GitHub
- **Goal**: Fix requirements, data contract, architecture, repo structure and first tasks *before* code.
- **Deliverable**: public repo **`plantvision-lab`** containing `README.md`, `ROADMAP.md`,
  `docs/architecture.md`, `docs/data-contract.md`, `docs/glossary.md`, `docs/decisions/0001-data-flow.md`,
  `pyproject.toml`, `configs/`, `.gitignore`, `data/README.md`, plus the initial GitHub Issues.
- **Acceptance (verifiable)**:
  1. `gh repo view MariganMarigam/plantvision-lab` returns the public repo; default branch `main`.
  2. `docs/data-contract.md` defines the 7 required observation fields (`reflection.md:233-244`), the
     `captured_at` (device) vs `received_at` (server) split (`reflection.md:586`), sha256 idempotency, and the
     4 storage entities (`reflection.md:579-584`).
  3. `docs/architecture.md` contains a data-flow diagram (phone → server → CV → history → UI).
  4. `docs/decisions/0001-data-flow.md` records the ADR: pull via IP Webcam, 10-min cadence, filesystem+SQLite.
  5. `ROADMAP.md` lists stages 00–08 with the same acceptance criteria as this file.
  6. ≥ 5 GitHub Issues exist with labels `stage-0`, `docs|infra|data`, `P0|P1`.
  7. An **uncertainties list** (open questions) is committed and linked from `README.md`.
- **Deps**: none (entry). Blocked on human gate **G1**.
- **Theory map**: `practic_CV.txt:2328` (§5.5–5.6 levels of representation / system architecture),
  `practic_CV.txt:1919` (§4.4 edge computing & architecture); `reflection.md:22-50` (target architecture),
  `reflection.md:233-249` (observation fields), `reflection.md:600-635` (repo layout).
- **Est**: M.

## Stage 01 — Image lab
- **Goal**: A reproducible Python environment and a notebook that loads a plant photo, inspects its
  shape/dtype/channels, and converts between RGB, HSV, grayscale — the measuring instrument for everything later.
- **Deliverable**: `.venv` + `cv_farm` packages pinned in `pyproject.toml`; `curriculum/01-image-fundamentals/`
  notebook; minimal `src/plantvision/vision/` helpers; `tests/`.
- **Acceptance (verifiable)**:
  1. `.venv/bin/python -c "import cv2, numpy, matplotlib; print(cv2.__version__)"` prints a version.
  2. Notebook loads a sample image and prints `(H, W, C)` and dtype; saves a processed copy to `output/`.
  3. HSV hue channel is shown separately from Value (`plan_practic_CV.txt:16`).
  4. `pytest` passes for the image-IO tests.
- **Deps**: Stage 00 (repo) — code lives inside `plantvision-lab`.
- **Theory map**: `practic_CV.txt:15` (§1.1 what is CV), `practic_CV.txt:73-241` (§1.2 image representation,
  RGB↔HSV↔Lab, HSV comparison at `159-178`), `practic_CV.txt:551` (§1.7 fundamental image operations),
  `practic_CV.txt:2060` (§5.1 image geometry), `practic_CV.txt:2470` (setup walk-through).
- **Est**: S.

## Stage 02 — Capture stand & shooting protocol
- **Goal**: A physically fixed phone framing one plant identically every time, with a stable in-frame scale
  reference, and the ability to record a comparable test series at the 10-min cadence without any CV model.
- **Deliverable**: fixed mount config (`configs/capture.yaml`), pull client + scheduler entrypoint,
  local reconnect queue, metadata sidecar, originals written under `data/originals/`.
- **Acceptance (verifiable)**:
  1. Two captures 10 minutes apart differ only by the plant (same framing) — visually confirmed.
  2. `capture_once` writes a JPEG + a JSON sidecar with `captured_at`, `camera_id`, `zone_id`, `sha256`.
  3. A forced network failure is retried and eventually ingested without a duplicate (idempotent by sha256).
  4. A scale reference (ArUco marker or ruler) is present in every frame (`reflection.md:489`).
- **Photoperiod (D8)**: capture runs only inside the configured light window (default 06:00–22:00 local); frames
  outside it are skipped (`dark_policy: skip`). Night spectral imaging needs a different camera → deferred.
- **Deps**: Stage 01.
- **Theory map**: `practic_CV.txt:242-303` (§1.2/1.3 distortions, lighting, occlusion — farm-specific),
  `practic_CV.txt:444-490` (static vs mobile camera), `practic_CV.txt:2711` (camera connection walk-through);
  `reflection.md:70-74` (stand), `reflection.md:445-471` (why pull + 10 min).
- **Est**: M.

## Stage 03 — Ingestion & durable storage
- **Goal**: A phone-independent, restart-safe pipeline that accepts an image, validates it, stores the original,
  records metadata, and never duplicates on re-send.
- **Deliverable**: ingest module + SQLite schema + idempotent receive path.
- **Acceptance**: images can be submitted, found by `image_id`, and recovered after a restart; re-sending the
  same bytes inserts one row (`reflection.md:527-529`).
- **Deps**: Stage 02.
- **Theory map**: `practic_CV.txt:533` (§1.6 datasets / data strategy); `reflection.md:76-80`, `reflection.md:573-598`.
- **Est**: M.

## Stage 04 — Automated 10-minute capture
- **Goal**: The scheduler on Ubuntu drives the cadence; capture time, connection errors and missed frames are logged.
- **Deliverable**: cron/systemd timer + logging of planned vs actually-received frames.
- **Acceptance**: the system shows planned vs real frames, and gaps are never silent (`reflection.md:539`).
- **Photoperiod (D8)**: the timer runs 24/7 but `capture_once` self-gates to the light window; dark-window runs
  exit `skipped_dark` (no capture, no gap). Night analysis deferred.
- **Deps**: Stage 03.
- **Theory map**: `reflection.md:82-86`, `reflection.md:445-471`; `practic_CV.txt:2711`.
- **Est**: M.

## Stage 05 — First growth measurer (no neural network)
- **Goal**: Segment the plant with classic OpenCV (HSV/ExG threshold + morphology), estimate capture quality,
  and compute projected area / ROI fraction; store the mask alongside the metric.
- **Deliverable**: vision module computing metrics + a reproducible projected-area plot with visible failure cases.
- **Acceptance**: a reproducible plot of projected area over a test series appears, and typical segmentation
  errors are documented (`reflection.md:547`).
- **Deps**: Stage 04.
- **Theory map**: `practic_CV.txt:315-397` (§1.3 segmentation & features; morphology at `366`),
  `practic_CV.txt:492` (§1.4 visibility enhancement), `practic_CV.txt:2111` (§5.2 morphology),
  `practic_CV.txt:2270` (§5.4 metrics), `practic_CV.txt:2274` (image-quality metrics).
- **Est**: L.

## Stage 06 — Dataset & model choice
- **Goal**: Collect representative images, label plant masks, split train/val/test, fine-tune a segmentation
  model, and measure its error against the classic baseline.
- **Deliverable**: versioned dataset + fine-tuned weights (local RTX 4060) + a hold-out evaluation.
- **Acceptance**: a separate validation set exists and the algorithm's error vs manual labels is measured
  (`reflection.md:555`).
- **Deps**: Stage 05.
- **Theory map**: `practic_CV.txt:1328` (§3.1 AI/ML fundamentals), `practic_CV.txt:1457` (CNN/RNN/Transformers),
  `practic_CV.txt:1606` (overfitting), `practic_CV.txt:1631` (augmentation), `practic_CV.txt:2293` (model metrics),
  `practic_CV.txt:3251` (dataset), `practic_CV.txt:3457` (fine-tuning), `practic_CV.txt:3721` (augmentation),
  `practic_CV.txt:4282` (instance segmentation).
- **Est**: L.

## Stage 07 — Temporal analysis & interface
- **Goal**: Turn per-frame measurements into time-series: daily/weekly charts, day-over-day change, latest
  images, and collector status.
- **Deliverable**: analytics module + read-only Streamlit viewer over SQLite.
- **Acceptance**: a selected period shows how a metric evolved without reviewing every photo (`reflection.md:563`).
- **Deps**: Stage 06.
- **Theory map**: `practic_CV.txt:411` (tracking/dynamics), `practic_CV.txt:4690-4975` (object tracking),
  `practic_CV.txt:1933` (§4.5 decision-support systems), `practic_CV.txt:2219` (§5.3 topology).
- **Est**: L.

## Stage 08 — Prototype validation & farm readiness
- **Goal**: Compare automatic measurements with manual ones, quantify accuracy and gap rate, document the
  conditions under which the system fails, then plan expansion.
- **Deliverable**: validation report + documented limits; expansion rules for multiple cameras/zones.
- **Acceptance**: accuracy, gap frequency, camera-placement requirements and failure conditions are known
  (`reflection.md:571`); the 6 prototype criteria in `reflection.md:645-650` are all demonstrable.
- **Deps**: Stage 07.
- **Theory map**: `practic_CV.txt:1086` (§2.4 localization/SLAM), `practic_CV.txt:1919` (§4.4 edge computing),
  `practic_CV.txt:2328` (§5.5–5.6 architecture); `reflection.md:106-110`, `reflection.md:641-650`.
- **Est**: L.

---

## Cross-cutting tracks (present in every stage)
Per `reflection.md:361-365`: **Data Engineering**, **MLOps** (model/experiment versioning), **Temporal CV**
(compare one zone across time). Gazebo/ROS/Sensor-Fusion (`plan_practic_CV.txt:66-102`,
`practic_CV.txt:582-1325`) is deferred to an advanced branch until a moving camera or sensor fusion is required
(`reflection.md:367`).

## Open questions (resolve before/at Stage 02)
Defaults proposed in `output/research/2026-10-13-phone-capture-minimal-stack.md` §Open questions;
resolution table lives in `plantvision-stage0-plan.md` §"Open-question resolutions".
