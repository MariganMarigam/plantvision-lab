# PlantVision — Forward Plan (2026-10-22)

> Author: Scout · Status: **APPROVED — decisions D1–D9 closed 2026-10-22; implementation-ready**
> Rev 2 (2026-10-22): D1–D8 incorporated; P1.3 (white-light series) added; P6 re-scoped to visual
> deficiency signs; the "lamp runs 24/7 / no dark period" claim is **retracted** (see §2.4, §9).
> Rev 3 (2026-10-22): **P1.5 (observability & provenance)** inserted between P1 and P2 (D9), folding in the
> vertical-farm OSS survey (`output/research/2026-10-22-vertical-farm-repos.md`): mask shape traits, MIAPPE-lite
> sidecar/CSV keys, coverage audit, camera-settings provenance. No code from the four named repos (idea-only /
> unlicensed); the metrics CSV gains **appended** columns, never a `crop_id` column.
> Repo: `plantvision-lab` @ `c52a5ef` (46 local commits ahead of `origin/main`)
> Sources: `output/CHECKPOINT-2026-10-18.md`, `output/handoff/LINUX-HANDOFF-2026-10-19.md`,
> `output/state/plantvision.md` (E31–E36), `output/plans/plantvision-{ml-lab,sam2-labeling,model-first-strategy,learning-loop,import-offline,roadmap}.md`,
> `output/research/2026-10-16-cv-models-and-phone-capture.md`, `QA.txt`.
> Everything marked **[verified 2026-10-22]** was re-checked in code/files on this Linux host.

---

## 0. Executive summary

The system is **data-rich and model-poor**: the capture → import → labeling → export chain is complete and
tested (199 tests, 46 local commits), but there is no ML environment on Linux, no labels, no trained model, and
the classical perception that anchors the baseline is **arithmetically incapable** of seeing the farm's
BLURPLE-lit plants (green-band fraction measured 0.0000 on 103 sampled frames).

Therefore the forward path is not "improve the classical baseline" — it is **stand up the Linux ML stack, let
SAM2 produce masks under human review, train a small student behind the already-frozen perception interface,
and gate promotion on held-out real frames.** Measurement (ArUco → px/mm → cm²) is untouched throughout; only
the mask-producing slot changes.

**Scope of this plan (per D1/D3):** one crop (**basil**), one metric (**projected area, cm²**). The label,
manifest and registry schema are **multi-crop-ready from day one** (a crop id travels with every frame, mask
and model) — but only the basil model is trained here, and no volume/biomass estimate is produced.

---

## 0.1 Approved decisions (2026-10-22)

These are **closed**; the phase plan below is written against them.

| # | Decision | Resolution | Where it lands |
|---|---|---|---|
| **D1** | Crop identity | **Basil.** Multiple crops exist on the farm, but the MVP targets **one** crop. Architecture must stay **multi-crop-ready**: every label/manifest row carries a `crop_id`; nothing hardcoded. | §P1.2 (schema), P2 (registry key), §7 (multi-crop training out of scope) |
| **D2** | White light | The farm **can** provide a white-light capture series **and** a white reference card. | New **P1.3**; **P4 unblocked**; white frames become the classical-segmentation sanity reference (§2.3) |
| **D3** | Measurement target | **Projected area only.** Volume / biomass deferred. | P3 comparison B (area only), §7 non-goals |
| **D4** | Disk | User frees space and allocates **20+ GB**. | P0 gate: ≥10 GB free before install, ≥8 GB after; cache redirection kept |
| **D5** | GitHub | Publishing the 46 local commits is **APPROVED** — separate Ivan task, *not part of this plan*. | §8 precondition (one line) |
| **D6** | Farm cadence | **5 minutes** stays. | P1 volume expectations unchanged (~192 lit frames/day) |
| **D7** | "Nutrients" | Means **visual deficiency / symptom signs only**. Chemical composition (EC, pH, N-P-K, any compound) is **explicitly out of scope for RGB**. | P6 renamed + re-scoped; §6, §7 |
| **D8** | Photoperiod | The farm **does have dark hours**. The 36 frames skipped by the light window are **correct**, not data loss. Verify the exact lights-off time; keep `dark_policy: skip`. | §2.1, §2.4, P1 gate, §6, §9 |
| **D9** | OSS survey | **Adopt the useful findings before P2:** PlantCV trait *formulas* (reimplemented, cited), MIAPPE 1.2 *vocabulary*, a dark-policy-aware coverage audit, and camera-settings provenance. **No code** from the four named repos (three unlicensed, one dead business-spreadsheet tool); no live dashboard, no second data store. | New **P1.5**; §3 "Adopted from OSS / rejected"; §6; §7 |

**Open, non-blocking** (no phase waits on these): target accepted-label count (**300 min / 500 stretch**) and
whether to label all 69 white-light home frames (recommended: yes — they are the only classical-comparable set).

---

## 1. Asset inventory — what already exists and works

### 1.1 Code (all in `plantvision-lab/`)

| Area | Path | State | Notes |
|---|---|---|---|
| Frozen contract | `src/plantvision/vision/interfaces.py:43,50,57` | ✅ frozen | `Perception`, `Fiducial`, `Measurement` Protocols + `check_mask` (`:65`) |
| Classical perception | `src/plantvision/vision/segmentation.py:90` | ✅ | HSV/ExG + morphology; config `configs/pipeline.yaml:11-14` |
| Fiducial (ArUco) | `src/plantvision/vision/scale.py:46` | ✅ | per-frame `DICT_5X5_50`, 45 mm (ADR-0002) |
| Measurement (geometry) | `src/plantvision/vision/metrics.py:196,236-243` | ✅ | mask → px → cm² via `px_per_mm²`; deterministic |
| Quality gates | `src/plantvision/vision/quality.py:93` | ✅ | blur/brightness/red-dominance (informational) |
| Capture / ingest / storage | `src/plantvision/{capture,ingest,storage,api}/` | ✅ | pull client, sidecars, idempotent by sha256, spool queue |
| Analytics / flywheel | `src/plantvision/analytics/` | ✅ | `timeseries.csv` append-only, idempotent |
| Offline import | `src/plantvision/capture/import_offline.py` | ✅ | EXIF>filename>mtime, dedupe, light window, flags |
| SAM2 labeling MVP | `src/plantvision/labeling/{frames,prompts,store,review,sam2_backend,export}.py` | ✅ code-complete, torch-lazy | proposals/decisions JSONL, review page, manifest, YOLO-seg export |
| CLIs | `scripts/{label_sam2,review_labels,build_label_manifest,export_labels,import_offline,update_metrics,measure_series,check_env,download_models,uninstall_ml}.py` | ✅ | `--help` works without torch (E36) |

### 1.2 Verified absences (do not assume these exist)

- **No `src/plantvision/vision/traits.py`, no `scripts/audit_coverage.py`, no `docs/provenance.md`** → all of
  P1.5 is new code (D9). `analytics/timeseries.py:27` currently has **15** columns and no provenance keys.
- **No `src/plantvision/perception/`** and **no `src/plantvision/ml/`** → the whole `ml-lab` plan's
  BACKENDS / LAB-RUNNER / DATASET / TRAIN / EVAL phases are **not implemented**.
- **No `configs/train.yaml`, no `configs/dataset.yaml`** (only `capture.yaml`, `capture-farm.yaml`, `models.yaml`, `pipeline.yaml`).
  There is also **no `configs/capture-white.yaml`** and **no crop field anywhere in code** [verified 2026-10-22:
  `grep -rn "crop" src/ | grep -v ROI-crop` → only `metrics.py:153-215` ROI cropping].
- **No `checkpoints/` directory**; `models/` is empty.
- **`.venv` is a Windows venv** (`Scripts/`, `Lib/`, no `bin/python`) → unusable on Linux.
- **`data/labels/v1/{masks,overlays}` exist but are empty**; 0 proposals, 0 decisions, 0 masks.
- `pytest` **cannot be run on this host today** (system Python 3.12 has numpy/PIL but **no cv2**; project deps live only in the dead Windows venv). 199 passed is the last verified count on Windows (E36); P0 must re-verify.

### 1.3 Data [verified 2026-10-22]

| Set | Location | Count | Facts |
|---|---|---|---|
| Farm source | `task/OpenCamera/` | **718 JPG** (172 MB) | 720×1280 portrait, 5-min cadence (714 gaps of 5 min), 2026-10-18 09:39 → 2026-10-21 18:24 |
| Farm imported | `plantvision-lab/data/originals/farm-01/farm_zone-a/` | **683** | 36 skipped by the 06:00–22:00 light window; 0 dupes/errors; `time_source=EXIF` |
| Home (white light) | `data/originals/phone-01/` | **69** | the only set where classical segmentation works today |
| White-light farm series | *to be captured — P1.3 (D2)* | **0 now** | target ≥50 frames + white card; same crop (basil) |
| Metrics | `data/derived/metrics/timeseries.csv` | home only | deliberately **not** run on farm (would write zeros, E36) |

**Skipped-frame reality [verified]:** the 718 files contain frames only in **06:00–22:59**; there are **zero**
frames between 23:00 and 05:59. The 36 window-skipped files are all **22:04–22:59** on three nights — i.e. the
farm's dark period is real (D8) and the window is directionally correct; only its 22:00 edge needs checking.

Disk: **20 GB free, 92 % used** at authoring time; the user will free space and allocate **20+ GB** (D4).
ML stack ≈ 5 GB installed + ~2.6 GB transient wheels → fits with ≥8 GB headroom after `pip cache purge`.

### 1.4 Tests and docs

- 32 test files, **199 passed** without torch (E36); labeling isolation is contractual
  (`tests/test_labeling_isolation.py`).
- Plans are unusually complete: `plantvision-ml-lab-plan.md` (env/models/backends/train/eval, SC-1…SC-8),
  `plantvision-sam2-labeling-plan.md` (artifact spec, split algorithm, acceptance 8.8),
  `plantvision-model-first-strategy.md` (P0–P4 model track), `plantvision-learning-loop-plan.md`,
  `plantvision-roadmap.md` (stages 00–08).

### 1.5 What works end-to-end today

capture/import (idempotent) → sidecars → sha-keyed frame scan (`labeling/frames.py:24-31`) → classical
perception + ArUco scale + measurement on **white-light** frames → `timeseries.csv` → plots. On farm frames the
chain runs but perception returns an empty mask, which is why the farm series was not generated.

### 1.6 Git state

`HEAD c52a5ef`, **46 commits ahead of `origin/main`**, nothing pushed. `gh` is authenticated as
`MariganMarigam` on this host. Every portfolio requirement in `QA.txt` depends on these commits reaching GitHub.
Publishing them is **approved (D5)** and is handled as a separate Ivan task — this plan does not touch git.

---

## 2. The BLURPLE constraint (the fact that reshapes the plan)

### 2.1 Measured, not assumed [verified 2026-10-22 on 103 stratified farm frames]

| Property | Value | Consequence |
|---|---|---|
| Channel means | R 176–188, G 46–55, B 174–185 | R ≈ B ≫ G → **magenta/blurple lamp**, not daylight |
| `R/G` (`quality.py:93-111` definition) | **3.4–3.9** | exceeds every red-light threshold; flag is informational only |
| Median hue (OpenCV 0–180) | **149.6–150.4** | magenta sits far outside the green band |
| Green-band fraction (HSV 25–95, S>40, V>40) | **0.0000** on all samples | classical mask is empty on **every** farm frame |
| Gray mean, 06:00–22:59 | **99.5–109.7** (median 104.9), flat within the lit window | exposure is stable while the lamp is on — luminance (not hue) is the usable channel |
| Dark hours | **present** — no frames 23:00–05:59 exist; the 36 skipped files are 22:04–22:59 and still lit | the light window is correct in principle (D8); its 22:00 edge is ~1 h early → verify exact lights-off |

### 2.2 Why the classical path cannot be tuned into working

- HSV band `[25,40,40]–[95,255,255]` (`configs/pipeline.yaml:12-13`) covers hue 50°–190°. Plant hue is ~300°.
  Widening the band to magenta would also select the **lamp, walls and background**, because they share the
  illuminant's chromaticity — the signal is not separable by hue under a monochromatic-ish source.
- ExG `2G − R − B` (`pipeline.yaml:14`) evaluates to **≈ −260** on these frames (2·51 − 182 − 180), versus a
  threshold of +20. No threshold in a sane range recovers leaves.
- The plant is lit by magenta light it mostly **absorbs** in G; whatever reflects is R+B. Chromatic plant/background
  separation is destroyed; **luminance/geometry survive**.

### 2.3 What still works perfectly

| Component | Status on blurple | Why |
|---|---|---|
| ArUco fiducial | ✅ 23/24 sampled detected, ~3.27–3.29 px/mm | corner detection is grayscale/contrast-based |
| Scale → cm² | ✅ 32.7–32.9 px/cm → **1070–1082 px²/cm²** | pure geometry; independent of colour |
| Quality gates (blur/brightness) | ✅ brightness 100–110, stable exposure | luminance is well-behaved |
| Timestamps / idempotency / EXIF | ✅ | capture-layer, colour-blind |
| Learned perception | ✅ (untested) | SAM2/segmentation nets key on shape/texture, not on the green band |
| Classical perception | ✅ **on white light only** — now also testable on the farm's own white series (P1.3) | hue separation exists under white LED; this is the segmentation **sanity reference** |

### 2.4 Implications

1. **The classical result is not a valid A/B baseline on farm frames.** Comparing a learned mask to an empty
   mask yields IoU 0 and meaningless Δarea. On blurple, the reference must be **reviewed SAM2 masks**; the
   classical baseline is comparable only on **white-light** frames (69 home + P1.3 farm-white series).
2. **SAM2 prompting degrades silently.** `scripts/label_sam2.py:130-131` falls back to `full_frame_box` when the
   HSV ROI prior (`labeling/prompts.py:16`) returns `None` — which on blurple is **always**. SAM2 will then
   segment "the most salient thing in the frame", which may be a tray, a wall or the lamp. This is the single
   biggest quality risk in P1 and must be probed before batch labeling.
3. **The 36 clock-skipped frames are correctly skipped (D8, corrected).** The farm does have dark hours: no
   frames exist 23:00–05:59. The 36 files in question are 22:04–22:59 and happen to be still lit, so the
   **22:00 edge** of `light_window` (`configs/capture-farm.yaml:29-31`) is probably ~1 h early. That is a
   tuning question, not data loss: **do not re-import**, keep `dark_policy: skip`, and verify the actual
   lights-off time before touching the window (§9 item 2).
4. **Colour is not a measurement channel here.** Any "hue trend" or colour-index nutrient proxy is invalid under
   blurple. Colour-based **visual** inspection is possible only in the white-light domain (P1.3 → P6), and even
   there it yields *signs*, never chemistry (D7).
5. **The mask is the only thing that must change.** Contract, fiducial, measurement and plots stay byte-identical
   (`interfaces.py` frozen; `metrics.py` arithmetic untouched, apart from P1.5's additive trait fields). The
   metrics CSV header is **append-only extended** in P1.5 (9 shape-trait + 9 provenance columns after `scale_ok`,
   with a one-time prefix-preserving migration of old rows); `crop_id` still travels in sidecar + manifest +
   experiment registry and never enters the metrics row (deferred until a second crop is actually trained).

---

## 3. Phased forward plan

Conventions: **S** <30 LoC / 1 file, **M** 30–100 LoC / 1–3 files, **L** 100+ / 3+ files. Each phase has an
**exit gate** that is a command or a counted artefact — no phase advances on "looks good".
Two fixed axes: **crop = basil** (D1) and **metric = projected area only** (D3). Any step that would need a
second crop or a volume estimate is explicitly out of scope (§7).

### P0 — Linux ML environment (est S/M; mostly download time; owner Ivan)

**Goal:** a reproducible GPU lab on this host, with the ML stack installed *outside* the measurement path.

**Work:**
1. Confirm disk headroom **before** anything else: `df -h .` → **≥10 GB free (D4)**. If less, stop and report;
   do not "just try" — a half-installed torch is worse than none.
2. Remove the Windows venv (`.venv/` — verified `Scripts/`, no `bin/`), then:
   `python3.12 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`.
3. Export cache redirection for the session so nothing lands outside the repo:
   `export HF_HOME=$PWD/models/hf TORCH_HOME=$PWD/models/torch YOLO_CONFIG_DIR=$PWD/models/ultralytics PIP_CACHE_DIR=$PWD/models/pipcache`.
4. `CUDA_CHANNEL=cu126 bash deploy/linux/setup-ml.sh` (script pins torch from the CUDA index, sam2 @
   `2b90b9f…`, ML extras; aborts below 3 GB free — `deploy/linux/setup-ml.sh:13-31`). Fallback order:
   `cu124` → `cpu` (only if CUDA is impossible; SAM2 on CPU is ~20–40× slower and P1 becomes overnight work).
5. `pip cache purge` after torch; verify free space **≥8 GB** at the end (D4 budget, not the script's 3 GB floor).
6. `python scripts/check_env.py --require-cuda`.
7. `python scripts/download_models.py` then `--record-hashes` (TOFU → pinned).
8. `pytest -q`.

**Gate P0 (all must hold):**
- pre-install `df` showed **≥10 GB** free; post-install **≥8 GB** free (record both numbers in the run log);
- `.venv/bin/python -c "import torch;print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"` → `True NVIDIA GeForce RTX 4060 Laptop GPU`.
- `scripts/check_env.py --require-cuda` exits 0 and prints VRAM.
- `pytest -q` → **199 passed** (no torch-dependent skips turned failures).
- `models/sam2.1_hiera_small/sam2.1_hiera_small.pt` exists with a `.sha256` sidecar (note the nested path:
  `scripts/download_models.py:7,70` stores `<storage_dir>/<name>/<filename>`, **not** the `checkpoints/…`
  default hardcoded in `scripts/label_sam2.py:32`).
- `git status` clean apart from ignored model/data paths.

### P1 — SAM2 zero-shot labeling on farm frames (est M + 2–4 h human review; owner Ivan + user)

**P1.0 Probe (mandatory, cheap):**
`python scripts/label_sam2.py --originals data/originals/farm-01 --limit 40 --device cuda --checkpoint models/sam2.1_hiera_small/sam2.1_hiera_small.pt`
then inspect `data/labels/v1/proposals.jsonl`.

**Gate P1.0 (decides whether to continue or fix prompts first):**
- 40 proposals written, 0 errors;
- `box_source` distribution recorded; **if `full_frame` ≥ 80 % and the visual accept rate on the review page is
  < 50 %**, STOP and do P1.1 before any batch run.

**P1.1 (conditional, only if P1.0 fails; est M):** give Ivan a prompt prior that works without green. Spec:
- `labeling/prompts.py` — add `prior_box(image_bgr, *, strategy="classical"|"full"|"manual", box=None)`; default
  remains classical so toy/white data is unaffected;
- `scripts/label_sam2.py` — add `--box x1,y1,x2,y2` and `--box-strategy {classical,full,manual}`; proposals must
  record the actual `box_source` (already a field, `:54`);
- alternative automatic prior if manual boxes are unacceptable: brightness/saturation ridge + largest connected
  component, **measured against 10 hand-checked frames before adoption**;
- tests: `tests/test_labeling_prompts.py` gains manual-box clipping/validation cases; isolation test still passes.
Do not change the mask store, manifest, or export formats.

**P1.2 Batch labeling + review (plus the crop-id plumbing of D1):**
1. **Carry the crop id (D1).** Three hops, in this order:
   a. import: `crop_id` read from the config (`crop_id: basil` in `configs/capture-farm.yaml`) and written into
      each sidecar by `build_metadata` (`capture/import_offline.py:217`);
   b. proposal: `scripts/label_sam2.py` copies the frame's `crop_id` into every proposal record it writes
      (next to the existing `model`/`checkpoint`/`box_source` fields, `store.py:281-283`);
   c. manifest: `"crop_id"` is **appended as the last** entry of `MANIFEST_COLUMNS` (`store.py:26-43`) and
      copied in `build_manifest` (`store.py:312-333`). Appending (never inserting) keeps every
      `csv.DictReader` consumer working; `tests/test_labeling_manifest.py:52,159` derives from the constant,
      so it stays green by construction.
   If a frame or proposal has no `crop_id`, the manifest writes `"unknown"` — **never** a silent `"basil"`
   default, and `build_label_manifest` warns with the count. `crop_id` does **not** enter the frozen metrics
   CSV (`scripts/measure_series.py:28-32`).
2. Run over the full farm set (or `--limit 300` first), stratified by date.
3. `python scripts/review_labels.py --labels data/labels/v1` → Accept/Reject each proposal in the browser.
4. `python scripts/build_label_manifest.py --labels data/labels/v1 --split-strategy group`
   (group split on `group_key = camera/zone/date`, `store.py:202-203,271`; temporal split would leak day-level
   lighting/exposure across splits).
5. `python scripts/export_labels.py --labels data/labels/v1 --out data/labels/v1/export/yolo-seg`
   (single polygon per mask, `export.py:19-22,76`).

**Gate P1:**
- **≥ 300 accepted farm masks** (stretch 500), **≥ 60 accepted per capture date** (4 dates), rejection rate recorded;
- **every accepted manifest row has `crop_id == "basil"`** (0 `unknown` in the accepted set; awk/csv check on
  `manifest.csv`), and the header's last column is `crop_id`;
- `build_label_manifest` prints **no "group spans splits" warning**;
- export: number of `.txt` labels == accepted count; every image has a label file and vice versa; polygons
  non-degenerate (no label with <3 points);
- 10 random accepted masks visually reviewed by the user against the plant silhouette, with notes in
  `data/labels/v1/review-notes.md`;
- **the 36 window-skipped frames are NOT re-imported** (D8) — the run log records the decision and the reason;
- `pytest -q tests/test_labeling_isolation.py` passes: `:47` proves labeling modules import in a fresh
  subprocess with torch absent, `:64` proves no CLI has a top-level torch/sam2 import. This guard must stay green
  **after** torch is installed (P0 does not relax it).

### P1.3 — White-light reference series + white card (est S code / 1 capture session; owner user + Ivan)

**Why:** D2 gives us a white-light series; it is the only way to (a) compare domains in P4, (b) prove the
classical segmentation still works on *this* farm's geometry, and (c) give P6 a colour-valid domain (D7).
This phase can run **in parallel with P1.2** — it blocks nothing before P3.

**Capture protocol (user, ~30 min):**
1. Same rig geometry as the farm camera (top-down, same working distance), same plant species = **basil**.
2. **White LED only** — blurple lamp off, no mixed lighting, no daylight through a window.
3. ArUco `DICT_5X5_50`, 45 mm, visible and in-plane in **every** frame (same marker as farm-01, ADR-0002).
4. **≥50 frames**, across **≥2 sessions on ≥2 days**, so exposure drift is visible; ≥10 of them with a
   **white/grey reference card** covering ≥10 % of the frame *and* with the marker visible.
5. Export as JPEG + sidecars naming `camera_id: farm-white-01`, `zone_id: farm/zone-a-white`, `crop_id: basil`.
6. Deliver on the same USB path so `import_offline` can ingest it unchanged.

**Work (Ivan):**
1. `configs/capture-white.yaml` modelled on `capture-farm.yaml` with `crop_id: basil`, `light_window`
   disabled (`00:00`–`23:59`) — the series is captured inside the farm's lit hours anyway.
2. `python scripts/import_offline.py --config configs/capture-white.yaml --source <usb dir> --dry-run`, then
   the real run. No code change expected; if `crop_id` is not yet accepted by `import_offline` (P1.2 step 1
   lands first), add it as a pass-through sidecar key only.
3. Run classical perception over the series:
   `python scripts/update_metrics.py --config configs/pipeline.yaml --originals data/originals/farm-white-01`
   (writes its own dir under `data/derived/metrics/`; **do not** merge into the farm series).

**Gate P1.3:**
- ≥50 imported frames, `time_source=EXIF`, 0 duplicates, 0 errors, `crop_id=basil` on every sidecar;
- **classical segmentation produces a non-empty mask on ≥45/50 frames** (90 %) with `area_fraction` in
  `[0.02, 0.60]` — recorded as a table in `output/research/`;
- ≥10 white-card frames stored under `data/originals/farm-white-01/.../reference/`; measured mean-channel
  ratios `R/G` and `B/G` are **within ±10 % of 1.0** after gray-world normalization (else the "white" light is
  not white — report it, do not paper over it);
- ArUco detection rate ≥95 % and px/mm within ±5 % of the blurple value on the same rig (otherwise the two
  domains are not geometrically comparable and P4 must say so);
- the 69 home frames remain untouched and still produce their existing metrics CSV.

### P1.5 — Observability & provenance (est S/M; owner Ivan) — *cheap, prevents false conclusions*

**Why:** four findings from the OSS survey map onto gaps we can close in under a day. Shape traits separate
wilting from growth (area alone cannot: a canopy can hold its footprint while its solidity collapses). MIAPPE
vocabulary makes every row joinable and publishable. A coverage audit makes "no data" distinguishable from
"no change". Camera settings explain step changes that are not growth. None of it touches measurement arithmetic,
the GPU, the frozen contract, or adds a dependency. Source: `output/research/2026-10-22-vertical-farm-repos.md`
(N1–N3, G1–G3).

**Entry:** any time after P0 (`pytest` must run). **Blocks nothing.** **Must land before P2** so every training
comparison is made on trait-bearing, provenance-bearing rows.

#### P1.5.1 Shape traits — CREATE `src/plantvision/vision/traits.py`

Pure cv2/numpy, no new dependency, no import of PlantCV.

- Frozen dataclass `ShapeTraits`: `hull_area_px: float`, `solidity: float`, `perimeter_px: float`,
  `ellipse_major_px: float`, `ellipse_minor_px: float`, `extent: float`, `n_components: int`.
- `def compute_traits(mask: np.ndarray) -> ShapeTraits | None` — accepts a uint8 `(H, W)` mask with values
  0/1 or 0/255. Formula source is the *documented definition* (PlantCV, MPL-2.0 — cited in the module
  docstring; **no code copied**). Steps, in order:
  1. Normalise to 0/255 uint8. If no foreground pixel → return `None`.
  2. `contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)`.
  3. `c = max(contours, key=cv2.contourArea)`; `contour_area = cv2.contourArea(c)`; if `<= 0` → `None`.
  4. `hull_area_px = cv2.contourArea(cv2.convexHull(c))`;
     `solidity = 0.0 if hull_area_px == 0 else clamp(contour_area / hull_area_px, 0.0, 1.0)`.
  5. `perimeter_px = cv2.arcLength(c, True)`.
  6. Equivalent ellipse: if `len(c) >= 5`: `(_, (w, h), _) = cv2.fitEllipse(c)` →
     `ellipse_major_px = max(w, h)`, `ellipse_minor_px = min(w, h)` (full axis lengths — **do not halve**);
     else both `0.0`.
  7. `_, _, bw, bh = cv2.boundingRect(c)`; `extent = 0.0 if bw * bh == 0 else clamp(contour_area / (bw * bh), 0.0, 1.0)`.
  8. `n_components`: `cv2.connectedComponentsWithStats(mask, connectivity=8)`; count labels ≥ 1 with
     `area >= 0.005 * foreground_px`; 0 foreground → 0.
- Determinism: same mask in → bit-identical `ShapeTraits` (no randomness, no float ordering surprises).

**Wire-in (do not change existing arithmetic):**
- `vision/metrics.py:75` `FrameMeasurement` gains 7 optional fields (default `None`/`0`); `measure_frame`
  (`:196`) calls `compute_traits(mask)` once after segmentation. `_cm_metrics` (`:177`) is untouched.
- Scale conversion happens in the row builder, not in `traits.py`: `hull_area_cm2 = hull_area_px / (ppm**2) / 100.0`,
  `perimeter_cm = perimeter_px / ppm / 10.0` (same convention as `_cm_metrics`); blank when `ppm is None`.
- `analytics/timeseries.py:27` `TIMESERIES_COLUMNS` — **append only**, after `scale_ok`, in this order:
  `solidity, hull_area_px, hull_area_cm2, perimeter_px, perimeter_cm, ellipse_major_px, ellipse_minor_px,
  extent, n_components`.
- `FLOAT_DECIMALS` (`:34`) adds `solidity: 4, hull_area_px: 2, hull_area_cm2: 3, perimeter_px: 2,
  perimeter_cm: 3, ellipse_major_px: 2, ellipse_minor_px: 2, extent: 4` (`n_components` is an int).
- **Header migration (mandatory — without it the first post-P1.5 row corrupts the CSV):**
  - file absent → write header = `TIMESERIES_COLUMNS` (unchanged behaviour);
  - header == `TIMESERIES_COLUMNS` → no-op;
  - header is a **strict prefix** of `TIMESERIES_COLUMNS` → pad every existing row with `""` for the new
    columns, write to a temp file in the same directory, `os.replace`; log `migrated N rows (+K columns)`;
    **appends no rows**;
  - any other mismatch → `ValueError` naming both headers; never silently drop a column.
- Empty mask → 9 blank cells — not `0`, not `nan`, not `inf` (blank = "not measurable"; 0 = "measured zero").

**Tests — CREATE `tests/test_vision_traits.py`:**
- filled 100×100 white square → `solidity == 1.0 ± 1e-6`, `extent == 1.0 ± 1e-6`, `perimeter_px == 400 ± 2`,
  `abs(ellipse_major_px - ellipse_minor_px) <= 1`, `n_components == 1`;
- "comb" (100×100 square minus three 20×40 notches) → `solidity < 0.95` and `extent < 1.0`;
- all-zero mask → `compute_traits(...) is None`, and the row builder emits `""` for all 9 trait cells;
- single-pixel mask → `n_components == 1`, `perimeter_px >= 0`, no exception;
- determinism → two calls compare equal (frozen dataclass).
- `tests/test_analytics_timeseries.py` gains: legacy 15-column CSV → run_update migrates the header, pads old
  rows, appends **0** rows; a new-column row round-trips; `crop_id` is still absent from the header.

#### P1.5.2 MIAPPE-lite provenance — MODIFY `capture/metadata.py:13`

- `build_metadata(...)` gains **keyword-only**, all defaulting to `None`:
  `experiment_id, biosource_id, observation_unit_id, treatment_id, light_regime, exposure_s, white_balance,
  gain_db, settings_source`.
- Always emitted (value or JSON `null`). Never required, never inferred, **never defaulted to `"basil"`**.
- Vocabulary (cite MIAPPE 1.2, `github.com/MIAPPE/MIAPPE`, doi:10.1111/nph.16544 — field *names* only, no prose):

  | our key | MIAPPE concept | example |
  |---|---|---|
  | `experiment_id` | experiment / investigation | `basil-2026-10` |
  | `biosource_id` | biological source (species/cultivar) | `basil-genovese` |
  | `observation_unit_id` | observation unit (zone + slot) | `farm/zone-a/slot-1` |
  | `treatment_id` | treatment / factor level | `led-blurple-18h` |
  | `light_regime` | environmental variable: photoperiod/spectrum | `blurple-18/6` |
  | `exposure_s`, `white_balance`, `gain_db` | measurement-device settings | `0.02`, `auto`, `null` |
  | `settings_source` | provenance of the three above | `exif` \| `app` \| `manual` \| `unavailable` |

- `crop_id` (D1, delivered in P1.2) stays the primary crop key; `biosource_id` is the MIAPPE-grained cultivar.
  If both exist and disagree, the sidecar keeps both and `import_offline` warns once per batch — it must not fail
  the import.
- CSV: `analytics/timeseries.py:27` **appends** `experiment_id, biosource_id, observation_unit_id, treatment_id,
  light_regime, exposure_s, white_balance, gain_db, settings_source` after the trait columns;
  `exposure_s: 4` and `gain_db: 2` join `FLOAT_DECIMALS`, the rest are strings in `_row` (`:127`).
- `_read_sidecar` (`:64`) and `FrameRecord` (`:38`) use `.get(key, "")` everywhere → a legacy sidecar without
  the 9 keys yields 9 empty cells, not a `KeyError`.
- Docs: `docs/provenance.md` = the table above + a "reserved, not yet captured" note. Attribution note names
  MIAPPE 1.2.

**Tests:** legacy sidecar (current 7 keys) → no error, 9 blanks; full sidecar round-trips; explicit `null`s →
`""` (documented as indistinguishable from absent); a sidecar with a non-null setting but missing
`settings_source` → `ValueError` (a setting without provenance is a false claim).

#### P1.5.3 Coverage audit — CREATE `scripts/audit_coverage.py`

CLI: `--csv data/derived/timeseries.csv --cadence-min 5 --dark-start 22:00 --dark-end 06:00 --max-missing 24
--max-gap-min 60 --out data/derived/coverage.md` (optional `--json`). stdlib + `csv` + `datetime` only.
Exit codes: **0** ok, **2** threshold exceeded, **1** usage/IO error.

- Group rows by `zone_id`; sort by `captured_at` (ISO-8601 `Z` ⇒ lexicographic == chronological).
- Expected grid on `cadence-min` from the zone's first to last timestamp (UTC). Each slot is classified
  `present` / `missing` / `outside_dark_policy` (slot start inside `[dark_start, dark_end)` local time — D8
  dark hours are expected, not gaps) / `undated` (rows with no `captured_at`).
- Per-zone report: rows, expected_slots, present, missing, outside_dark_policy, undated, duplicates (same
  `sha256` > 1), `longest_gap_minutes` + its start/end, `quality_flag != ok` count, `scale_ok == False` count,
  and `settings_unknown` count (from P1.5.4 — absence must be visible, not silent).
- Threshold rule: `missing > --max-missing` **or** `longest_gap_minutes > --max-gap-min` → mark the row `FAIL`,
  write the report anyway, exit **2**.
- Edge cases: < 2 rows → "insufficient data", exit 0; duplicate timestamps → one slot for coverage, reported
  separately; unsorted CSV → sorted internally; unparseable timestamp → `undated`, never crash; empty CSV →
  "no rows", exit 0. `--dark-*` defaults come from `configs/capture-farm.yaml:29-31` when present, else disabled.

**Tests — CREATE `tests/test_audit_coverage.py`:** 24 h fixture at 5 min = 288 slots.
- 3 slots deleted inside the lit window → `missing == 3`, `longest_gap_minutes == 15`;
- 1 slot deleted inside the dark window → `outside_dark_policy == 1`, `missing == 0`;
- duplicated `sha256` → `duplicates == 1`, `missing` unchanged;
- `--max-missing 2` → exit 2; `--max-missing 3` → exit 0;
- < 2 rows → exit 0 with "insufficient data".

#### P1.5.4 Camera settings in the capture path (measurement-integrity, not a nice-to-have)

- **MODIFY** the `build_metadata` call site in `capture/import_offline.py:217`: read EXIF `ExposureTime`,
  `WhiteBalance` (and `ISOSpeedRatings`) when present → `exposure_s`, `white_balance` (`auto` | `manual`).
  `gain_db` stays `null` for phone EXIF (no documented ISO→dB conversion); do not invent one.
- `settings_source` = `exif` when at least one of the three settings is present, `unavailable` otherwise.
  **Never guess a setting.**
- When `settings_source == "unavailable"`, `quality.py` is untouched, but the audit report counts
  `settings_unknown` per zone so the gap is visible.
- **Rationale (goes in the docstring and the risk table):** under BLURPLE a white-balance change shifts the
  global R/B ratio and can move `area_cm2` with no change to the plant. A step change in area that coincides
  with a settings change is a **camera event** until proven otherwise.
- **Tests:** JPEG fixture with camera EXIF → `exposure_s` populated, `settings_source == "exif"`; fixture
  without → all null, `settings_source == "unavailable"`; non-null setting without `settings_source` →
  `ValueError` (same rule as P1.5.2).

**Gate P1.5 (all must hold):**
1. `pytest -q tests/test_vision_traits.py tests/test_analytics_timeseries.py tests/test_capture_metadata.py
   tests/test_audit_coverage.py` → green.
2. Fresh run over the farm tree: header equals `TIMESERIES_COLUMNS` exactly; the 9 trait columns are populated
   on ≥ 95 % of rows **that have a marker** (cm columns blank only where `ppm is None`); zero `inf`, zero `nan`.
3. **Idempotency:** an immediate re-run reports `appended == 0` and `rows_total` is unchanged; the header
   migration runs at most once and is a no-op on the second pass.
4. Audit: fixture numbers exact (`missing == 3`, `longest_gap_minutes == 15`); `data/derived/coverage.md`
   written for the real farm CSV; a demonstrated exit 2 with `--max-missing 0` on a holed fixture.
5. Provenance: a legacy sidecar and a legacy CSV both still load; the per-zone `settings_unknown` count is
   printed (non-zero today is a *finding*, not a failure).
6. **No measurement change:** `git diff --name-only HEAD -- src/plantvision/vision/interfaces.py
   src/plantvision/vision/scale.py` is empty, and `area_px` / `area_cm2` on a 50-frame sample are byte-identical
   before vs after P1.5.

#### Adopted from OSS / rejected (survey of 2026-10-22)

| Source | Licence | Adopted | Rejected |
|---|---|---|---|
| `danforthcenter/plantcv` | **MPL-2.0** | trait **formulas** only (hull, solidity, perimeter, ellipse, extent), reimplemented in `traits.py` with a citation | the package as a dependency; any copied source body (would make that file MPL) |
| `MIAPPE/MIAPPE` | CC-BY-SA-4.0 (docs) | **field names / vocabulary** (P1.5.2) | copied prose, the checklist text, the full model |
| Coverage auditing | — (idea) | missing vs `outside_dark_policy` vs present; duplicates; longest gap | interpolation / zero-padding of gaps |
| `kizniche/Mycodo`, `FarmBot/FarmBot-Web-App`, `Pragmatismo/Pigrow` | GPL-3.0 / MIT / GPL-3.0 | vocabulary and patterns only: Input/Function/Output, command→ack→log, date-grouped gallery, per-camera settings | all code (GPL/stack mismatch), live dashboards, relay control |
| `GaiaKnowledge/VerticalFarming`, `alexsteinerr/vertical-farm`, `gpappasv/Vertical-Farming`, `divyansh2111/Vertical-Farming-Optimizations` | MIT / **none** / **none** / **none** | **nothing** | **all code** — three are unlicensed (all rights reserved), the fourth is dormant since 2022 and is a business-risk spreadsheet tool; none does scale-correct measurement |
| `grafana/grafana`, `streamlit/streamlit` | AGPL-3.0 / Apache-2.0 | deferred as viewers, LATER (§7) | a live dashboard or a second data store in the MVP |

Rule: **steal algorithms and schemas, not stacks.** Every surveyed project that added a second store beside its
own history has an open bug about the two disagreeing; CSV + sidecar stays the single source of truth.

### P2 — Model selection + first training behind the frozen interface (est L; owner Ivan)

**Prerequisite:** the `ml-lab` BACKENDS/RUNNER/DATASET/TRAIN/EVAL phases are unimplemented (§1.2). P2 therefore
consumes `plantvision-ml-lab-plan.md` §5 phases in this order: BACK-1/2 + RUN-1..3 (registry + runner),
DATA-1..3 (dataset from the label store), TRAIN-1..3, EVAL-1..2. Keep its SC-1…SC-8 as the phase's internal gates.

**Multi-crop-ready registry (D1) — hard requirement, not a stub:**
- experiment dirs are `experiments/<crop_id>/<run>/`; registry keys are `"<crop_id>:<name>:<version>"`
  (e.g. `basil:segformer-b0:v1`);
- `get_perception(model_id)` resolves the key; at inference, **the frame's `crop_id` must equal the model's
  crop** or the call raises `ValueError` with both ids in the message (no silent fallback — the classical path
  is the only fallback, and only on white light for now);
- **no crop literal in `src/`**: `grep -rn '"basil"\|"lettuce"' src/` returns nothing; the string lives only in
  configs and tests. Parametrized test over `["basil", "lettuce"]` proves the plumbing is crop-generic without
  training a second model.

**Work:**
- Three candidates trained on the same manifest, same split, same 512–640 px input, AMP, batch sized to 8 GB:
  `segformer-b0`, `yolo11n-seg` (benchmark only), `dinov2-small + linear head`.
- All inference enters through `get_perception(name)` and must return a contract-valid mask (`check_mask`).
- `vision/metrics.py`, `vision/scale.py`, `vision/interfaces.py` **must not be modified** (assert with
  `git diff --name-only` in the gate).

**Gate P2:**
- training completes ≥1 full epoch on the 4060 with AMP; checkpoint + `config.yaml` + `metrics.json` under
  `experiments/basil/<run>/`; weight sha256 recorded in the registry under a `basil:` key;
- `python scripts/run_lab.py --backend basil:segformer-b0:v1 --originals data/originals/farm-01 --limit 20`
  produces `experiments/lab/<id>/{metrics.csv,comparison.md}` and all 20 masks pass `check_mask`;
- a manifest row with `crop_id=lettuce` fed to `basil:` model raises `ValueError` (tested), and
  `grep -rn '"basil"' src/` is empty;
- `git diff --name-only HEAD` shows **no** changes under `src/plantvision/vision/`;
- `pytest -q` green without torch (lazy imports preserved).

### P3 — A/B vs baseline on held-out real frames, gated promotion (est M; owner Ivan)

**Metric scope: projected area only (D3).** No volume, no biomass, no derived 3-D quantity enters any
comparison or gate here.

**Protocol (three comparisons, never mixed):**

| Comparison | Data | Reference | Purpose |
|---|---|---|---|
| A. Model vs reviewed labels | farm test split (group split) | accepted SAM2 masks | mask quality (Dice/IoU/Recall) |
| B. Δ projected area | farm test split | `measurement(model_mask, fiducial(img))` vs `measurement(ref_mask, …)` | does the *cm² metric* survive a mask swap |
| C. Model vs classical | 69 white-light home frames **+ the P1.3 farm-white series**, temporal/group split | classical mask | regression check on the only domain where classical is valid |

**Gate P3 (promotion thresholds — frozen before training, not tuned afterwards):**
- A: **Dice ≥ 0.85, IoU ≥ 0.75, Recall ≥ 0.90** on farm test;
- B: **median |Δarea_cm²| ≤ 5 %** and **p90 ≤ 10 %** vs reference; frames without a marker are excluded and counted;
- C: Dice vs classical **≥ 0.90** on white-light frames (no regression on the home domain); on the P1.3 series,
  classical must be non-empty (per P1.3 gate) or C is reported as "not computable" with the reason;
- no crash/OOM on any test frame; runtime ≤ 100 ms/frame at 720p on the 4060;
- promotion = new registry name (`basil:seg-v1`) + one-line config switch (`perception_model`); rollback to
  `classical` proven in the same session (run both, show both reports).

**If the gate fails:** do not promote. Record `experiments/<run>/gate.md` with failures, return to P1 (more
labels, harder frames) or P4 (normalization). The classical path stays the default.

### P4 — Domain robustness: blurple vs white, colour normalization (est M; owner Ivan + user)

**Goal:** one model that survives both illuminants, or an explicit per-domain registry entry.
**Unblocked:** the white-light series is a committed deliverable of P1.3 (D2), not an open question.

**Work:**
1. Use the **P1.3 series** as the white-light domain (≥50 frames, same crop, same rig) plus the 69 home frames
   as an out-of-rig white test set; keep them separate in the report.
2. Evaluate the P3 model on both domains without retraining (cross-domain matrix).
3. Add normalization *in front of* perception, never inside measurement: gray-world / white-balance (calibrated
   from the P1.3 **white card** frames), per-channel percentile stretch, CLAHE on V, optional hue-invariant
   input (e.g. normalized-rg channels). Each variant is a named backend so the comparison is reproducible.
4. If normalization is insufficient: domain randomization in training (colour jitter, magenta-shift, exposure
   jitter — `ml-lab` DATA-2 already scopes this) and/or a two-domain training mix.

**Gate P4:**
- cross-domain table with Dice for {blurple, white} × {model, model+normalization}, white split into
  {farm-white (P1.3), home (phone-01)};
- **Dice_blurple ≥ 0.80 and Dice_white ≥ 0.85** with a single promoted backend, and **cross-domain drop ≤ 0.10**;
- **no domain silently writes empty masks**: a zero-area mask must raise a quality flag, not a metric row —
  verified by a test that injects an all-zero mask and asserts no CSV row is written;
- white-card calibration changes channel ratios to within ±10 % of 1.0 without moving the ArUco px/mm by more
  than ±5 % (normalization must not touch geometry);
- decision recorded: one model for both domains, or two registry entries
  (`basil:seg-v1-blurple`, `basil:seg-v1-white`).

### P5 — Disease / symptom detection (est L; data-blocked; owner Ivan + user)

**Entry condition:** P3 promoted **and** ≥2 full growth cycles captured post-promotion. No entry before that.

**Scope (biotic / damage signs):** symptom *presence* on a segmented plant — lesions, necrosis patches, tip
burn, spotting, mould — as a patch/pixel classifier on top of the promoted mask. Output is advisory; it never
enters `measurement` or `timeseries.csv`. **Boundary with P6:** P5 owns pathogen/damage classes; P6 owns
nutrient-deficiency *patterns*. The class ontology is disjoint and versioned; a class may not exist in both.

**Gate P5:**
- ≥200 labelled symptom patches across ≥3 severity levels, split by date group;
- held-out precision and recall **≥ 0.70** per symptom class; confusion matrix published;
- false-positive rate on healthy frames **≤ 10 %**;
- every prediction carries the model version + mask provenance + `crop_id`; classical/rule fallback documented;
- zero overlap with the P6 class list (checked against the ontology file, not by eye).

### P6 — Visual deficiency / symptom-sign detection (renamed from "Nutrient / compound estimation"; est L; data-blocked; D7)

**What changed (D7):** "nutrients" was ambiguous. It now means **visual deficiency signs only**. Chemical
composition — EC, pH, N-P-K concentration, chlorophyll content, any compound — is **explicitly out of scope for
RGB** and is not attempted, proxied or approximated anywhere in this plan.

**Scope:** classify visible deficiency *patterns* on a segmented basil plant under **white light** (P1.3 domain;
colour is meaningless under blurple, §2.4.4) — e.g. uniform chlorosis, interveinal chlorosis, marginal/tip
necrosis, stunting signature. Output is advisory, carries a confidence band, and **never** enters
`measurement` or `timeseries.csv`.

**Honest statement of the limit (must appear in the deliverable, not the fine print):** a visual sign is not a
diagnosis and not a concentration. "Leaf looks N-deficient" is a hypothesis to be checked by the grower's
fertigation log, not a measurement. No RGB-derived number may be labelled EC/pH/N-P-K.

**Work:** freeze a deficiency-sign ontology (≥3 classes + healthy), collect labels on the white-light series and
post-P3 white captures, train a small classifier head on the promoted mask's crops, report per-class metrics and
calibration; every report states the domain (white) and the crop (`basil`).

**Gate P6:**
- ≥200 labelled deficiency instances across **≥3 deficiency classes + healthy**, split by date group, all
  `crop_id=basil`, all captured under white light (blurple frames are rejected by a schema check, not by eye);
- held-out per-class precision and recall **≥ 0.70**; confusion matrix + calibration (ECE ≤ 0.10) published;
- false-positive rate on healthy frames **≤ 10 %**;
- the report contains zero chemistry claims: automated check that the words EC/pH/N-P-K/ppm appear only in the
  out-of-scope statement;
- otherwise publish "visual signs not separable with RGB under this protocol" and stop — a negative result is
  the deliverable.

---

## 4. Model comparison and default recommendation

Sizes from `configs/models.yaml`; VRAM/speed are **estimates for 720×1280 on the RTX 4060 8 GB** to be measured in
P0/P2, not vendor claims. Accuracy is a **hypothesis to be tested at the P3 gate**, not a promise.
All models are **crop-agnostic architectures**: the crop selects the dataset and the registry key, never the
network design (D1).

| Model | Role | Licence | Size / VRAM (est) | Speed (est) | Expected accuracy (hypothesis) | Recommendation |
|---|---|---|---|---|---|---|
| **SAM2.1 hiera-small** (46 M) | **auto-labeler** | Apache-2.0 | 184 MB / ~2 GB | 0.1–0.3 s/frame | zero-shot Dice 0.60–0.80 on blurple; after human review → usable labels | **Default labeler.** Only producer of labels; never deployed |
| SAM2.1 hiera-base+ (81 M) | auto-labeler (fallback) | Apache-2.0 | 324 MB / ~3 GB | 0.2–0.5 s/frame | +2–5 Dice points if small under-segments | Fetch only if small fails the P1.0 probe |
| **YOLO11n-seg** (2.9 M) | student / deploy | **AGPL-3.0** | 6.2 MB / <1 GB | 2–5 ms/frame | Dice 0.85–0.93 after ~300 labels (same domain) | **Benchmark + speed reference only**; do not ship |
| YOLO26n-seg | student / deploy | **AGPL-3.0** | 6.7 MB / <1 GB | 2–5 ms/frame | similar to YOLO11n, NMS-free | Optional second benchmark; same shipping ban |
| **SegFormer-b0** (3.7 M) | **deployable student** | Apache-2.0 code; NVIDIA ADE20K checkpoint licence **to verify** | 15 MB / ~1 GB | 10–20 ms/frame | Dice 0.85–0.92 after ~300 labels | **Default deploy candidate** (permissive); use MiT/timm init if the checkpoint licence is unclean |
| SegFormer-b1 (13.1 M) | deploy (accuracy tier) | same caveat | ~54 MB / ~1.5 GB | 15–30 ms/frame | +1–3 Dice over b0 | Only if b0 misses the P3 gate |
| **DINOv2-small** ViT-S/14 (21 M) | frozen backbone + linear head | Apache-2.0 | 88 MB / ~1 GB | 8–15 ms/frame | Dice 0.70–0.85 (label-efficient, weaker boundaries) | Third opinion / low-label fallback; not the default deploy |

**Concrete default:** **SAM2.1-small as the automatic labeler → human review → SegFormer-b0 as the deployable
student, with YOLO11n-seg trained in parallel as the accuracy/speed benchmark.** Promote whichever passes P3;
keep classical as the fallback on white-light data and keep the AGPL weights out of any shipped artifact.
Rationale: SAM2 is the only permissive model that produces usable masks with ~1-click prompts; SegFormer-b0 fits
8 GB with room for batch + AMP and its licence allows shipping; YOLO tells us the accuracy ceiling of the smallest
possible model, which matters if this ever moves to a Jetson/Pi.

---

## 5. Decision log

D1–D9 closed 2026-10-22; see §0.1 for the binding text. Nothing in this plan is blocked on a user decision.
Open, non-blocking confirmations are listed at the end of §0.1 (label target 300/500; label the 69 home frames
or not). If a future capture set contradicts D8 (e.g. frames exist at 02:00 and are lit), reopen D8 rather than
silently editing the window.

---

## 6. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SAM2 full-frame prompts segment the wrong object on blurple | **High** | bad labels → bad model (garbage in) | P1.0 probe with a hard numeric stop; P1.1 manual/automatic prior; review page is mandatory |
| Reviewer fatigue → rubber-stamping | Medium | label noise, inflated Dice | 300-frame cap per session, overlay + score shown, 10-frame audit at the end, rejection rate tracked |
| Circularity: SAM2 labels become ground truth | Medium | model learns SAM2's biases | Accept/reject + manual polygon fix option; keep a hand-drawn 20-frame audit set outside the training pool |
| 8 GB VRAM / OOM during training | Medium | schedule slip | nano/b0 only, AMP, grad accumulation, batch 2–4; `--device cpu` path exists |
| Disk pressure during install | Medium | install aborts / system pressure | D4: 20+ GB allocated, ≥10 GB pre-check, ≥8 GB post-check, cache redirection, purge after torch |
| **Lights-off time unverified (22:00 edge may be ~1 h early)** | Medium | a few lit frames skipped per night; or dark frames imported if the window is widened carelessly | keep `dark_policy: skip`; measure gray mean on the 22:00–23:00 boundary over ≥5 nights before changing `capture-farm.yaml:29-31`; change only with evidence |
| White-light series delayed or not white | Medium | P4 cross-domain gate and P6 domain unavailable | P1.3 is a 30-min capture; white-card ratio check (±10 %) catches "white" lights that are not white; P4 falls back to home frames + explicit "single domain" decision |
| **Camera setting change masquerades as growth** (WB/exposure shift under BLURPLE moves the mask globally) | **Medium** | false growth/decline, wrong agronomy call | P1.5.4 records `exposure_s`/`white_balance`/`gain_db` + `settings_source`; any area step change coinciding with a settings change is treated as a camera event until disproven; `settings_unknown` counted per zone by the audit |
| **Gap blindness: "no data" read as "no change"** | **High** | a dead camera or skipped run looks like a stalled plant | P1.5.3 coverage audit on a 5-min grid with `missing`/`duplicate`/`longest_gap` per zone, non-zero exit on threshold; no interpolation, no zero-padding (the surveyed repos' failure mode) |
| Scope creep from the OSS survey (second store, dashboard, sensor layer) | Medium | time lost, two sources of truth | D9 fixes the adoption list; Mycodo/FarmBot/Grafana/Streamlit stay in §7 non-goals until a sensor/actuator exists |
| Multi-crop drift: basil labels quietly reused for another crop | Medium | wrong numbers on a second crop | `crop_id` in sidecar/manifest/registry; model↔frame crop mismatch raises `ValueError`; no crop literal in `src/` |
| AGPL contamination (YOLO) | Low | shipping problem later | YOLO is benchmark-only; never imported by `src/plantvision`, only by lab scripts |
| SegFormer checkpoint licence | Medium | ship blocker | verify before P2; fall back to MiM/timm MiT init (permissive) |
| Single plant/zone overfit (n=1 plant) | **High** | metrics that do not generalize | blurple+white domains, date-group splits, report per-group metrics; treat Dice as domain-specific |
| 46 unpushed commits lost/re-written | Low | portfolio + history | D5: push approved; separate Ivan task **before** P0 env surgery |
| Windows-venv leftovers break `pip install -e .` | Low | P0 friction | delete `.venv` outright; never reuse it |
| Metric drift from model swap | Low | bad agronomy data | measurement untouched; Δarea gate B in P3; `pipeline_version` in metrics stays honest |

---

## 7. Non-goals (explicitly out)

- **Chemical composition of any kind** (EC, pH, N-P-K, chlorophyll content, any compound assay or RGB→chemistry
  proxy) — out of scope for RGB (D7). Visual deficiency *signs* are P6; chemistry is a different instrument.
- **Volume, biomass, 3-D reconstruction** — projected area only in this plan (D3); stereo/multi-view needs hardware.
- **A second crop model.** Architecture is multi-crop-ready (D1), but only basil is trained and gated here.
- End-to-end VLM that outputs cm² (no scale, non-deterministic) — permanent.
- Autonomous self-training / pseudo-label loops without human review — permanent (learning-loop decision).
- solvePnP, 6-DoF pose, moving camera / robot / ROS branch — deferred until a moving rig exists.
- LAI from multiple cameras — needs hardware.
- Multispectral, chlorophyll-fluorescence or EC/pH sensors — separate instrument track.
- Night/dark-frame imaging or night spectral analysis — the farm has dark hours (D8); a dark-frame pipeline would
  be a new camera, not a new threshold.
- **A second data store (Mongo/Influx/Postgres) beside the CSV, and a live dashboard in the MVP** — every
  surveyed project that added one has an open bug about the two disagreeing; CSV + sidecars stay the single
  source of truth (Grafana/Streamlit defer until a sensor/actuator exists, D9).
- **Code copied from the four named CEA repos** (`GaiaKnowledge/VerticalFarming`, `alexsteinerr/vertical-farm`,
  `gpappasv/Vertical-Farming`, `divyansh2111/Vertical-Farming-Optimizations`): three are unlicensed
  (all rights reserved), one is dormant since 2022, none does scale-correct measurement. Ideas only — see the
  P1.5 "Adopted from OSS / rejected" table.
- Cloud/K8s/dashboard host; a second plant/zone before the first one is validated.
- Shipping AGPL weights; shipping any model before the P3 gate.
- Training foundation models from scratch on 8 GB.

---

## 8. Sequencing

```
D5 (push, separate Ivan task) ──> P0 (env, ≥10 GB free)
                                      └─> P1.0 probe ──[fail]──> P1.1 prior fix ──┐
                                                  └──[pass]──────────────────────┴─> P1.2 label 300 ──> P1.5 observability ──> P2 train
P1.3 white-light capture (user, parallel, P1.2–P2 window) ──────────────────────────────┐
                                                                                        v
                                                                   P3 gate (area-only) ──> P4 domain robustness
                                                                                        │
                                                                                        └──> P5 disease (data-blocked)
                                                                                        └──> P6 visual deficiency (white-light, data-blocked)
```

Critical path: **P0 → P1 → P1.5 → P2 → P3**. P1.5 is cheap (est S/M), touches no measurement arithmetic and
blocks nothing else, but it must land **before P2** so every training comparison runs on trait- and
provenance-bearing rows. P1.3 must be *campaign-complete* before P4 starts, but it is a capture
task, not an engineering task, and can run alongside P1.2/P2. P5/P6 are gated by captured growth cycles and
white-light labels, not by engineering.

---

## 9. Corrections to previously recorded facts (flag before reuse)

1. **`red_dominance` is 3.4–3.9 on farm frames**, not ~1.57 as written in E35 and
   `configs/capture-farm.yaml:43-44`. The definition is `mean(R)/mean(G)` (`quality.py:93-111`); measured R≈180,
   G≈51. Either the earlier value used a different ratio or it was mis-recorded. The flag still fires; only the
   number in the comment is wrong.
2. **RETRACTED: "there is no dark period / the lamp runs 24/7".** The farm **does** have dark hours (D8): the
   capture set contains **zero** frames between 23:00 and 05:59, and the 36 window-skipped files are all
   22:04–22:59. The correct statement is: *the 06:00–22:00 window is right in principle, its 22:00 edge is
   probably ~1 h early (those 36 frames are still lit), and the exact schedule is unverified.* Consequences:
   **do not re-import the 36 frames**, keep `dark_policy: skip`, and verify lights-off over ≥5 nights before
   editing `configs/capture-farm.yaml:29-31`. Any earlier plan step that called this "data loss" is withdrawn.
3. **`crop = basil` supersedes the older `crop=lettuce` note (E5/2026-10-13).** Labels, manifests and registry
   keys carry `crop_id`; the lettuce note is historical only (D1).
4. **`task/QA.txt` does not exist**; the requirements file is `/home/codexrescriptus/devel/CV/QA.txt`.
5. **The checkpoint path in `label_sam2.py:32` is stale** relative to `download_models.py` output
   (`models/<name>/<filename>`). Always pass `--checkpoint` explicitly until that default is fixed.
6. Raw farm count is **718** JPG [verified 2026-10-22 by `os.listdir` + extension filter; E35 said 719].
   683 imported + 36 window-skipped = **719**, i.e. one more than the folder contains — the arithmetic still
   does not close. Reconcile during P1 by sha comparison (not filenames), and record the result in the state
   ledger. Do not "fix" the count by re-importing.
7. **Metrics CSV has no crop column and will not gain one in this plan** (`scripts/measure_series.py:28-32`);
   `crop_id` lives in sidecar + manifest + registry. Revisit only when a second crop is actually trained.
   The header **does** grow in P1.5 (9 shape-trait + 9 provenance columns, appended after `scale_ok`) via a
   one-time prefix-preserving migration of existing rows (§P1.5.1) — additive only, never an insert.

---

## 10. Verification commands (copy-paste, post-P0)

```bash
cd plantvision-lab
df -h .                                        # gate P0: >=10 GB before, >=8 GB after
.venv/bin/python scripts/check_env.py --require-cuda
.venv/bin/python -m pytest -q
.venv/bin/python scripts/download_models.py --list
.venv/bin/python scripts/label_sam2.py --originals data/originals/farm-01 --limit 40 \
    --device cuda --checkpoint models/sam2.1_hiera_small/sam2.1_hiera_small.pt
.venv/bin/python scripts/review_labels.py --labels data/labels/v1
.venv/bin/python scripts/build_label_manifest.py --labels data/labels/v1 --split-strategy group
.venv/bin/python scripts/export_labels.py --labels data/labels/v1 --out data/labels/v1/export/yolo-seg
# P1 gate: every accepted row carries the MVP crop (header-driven, append-safe)
awk -F, 'NR==1{for(i=1;i<=NF;i++){if($i=="crop_id") c=i; if($i=="accepted") a=i}} NR>1 && $a=="1" && $c!="basil"{n++} END{print (n+0), "non-basil accepted rows"}' \
    data/labels/v1/manifest.csv               # expected: 0
# P1.3: white-light series + white card sanity
.venv/bin/python scripts/import_offline.py --config configs/capture-white.yaml --source <usb-dir> --dry-run
.venv/bin/python scripts/update_metrics.py --config configs/pipeline.yaml --originals data/originals/farm-white-01
# P1.5: shape traits, provenance, coverage audit
.venv/bin/python -m pytest -q tests/test_vision_traits.py tests/test_analytics_timeseries.py \
    tests/test_capture_metadata.py tests/test_audit_coverage.py
.venv/bin/python scripts/audit_coverage.py --csv data/derived/timeseries.csv --cadence-min 5 \
    --dark-start 22:00 --dark-end 06:00 --max-missing 24 --max-gap-min 60 --out data/derived/coverage.md
.venv/bin/python -c "import csv;h=next(csv.reader(open('data/derived/timeseries.csv')));print(h[-9:])"  # 9 provenance cols
.venv/bin/python -c "import csv;h=next(csv.reader(open('data/derived/timeseries.csv')));print('crop_id' in h)"  # False
# P2: no crop literal in source, frozen vision modules untouched
grep -rn '"basil"\|"lettuce"' src/ || echo "OK: crop-agnostic source"
git diff --name-only HEAD -- src/plantvision/vision/   # expected: empty
```

---

### Output Enhancement
- 🔍 CodeGraph: `vision/metrics.py:75,196` (`FrameMeasurement` + `measure_frame` — P1.5 wire-in point),
  `analytics/timeseries.py:27,34,127,207` (`TIMESERIES_COLUMNS`, `FLOAT_DECIMALS`, `_row`, `run_update`),
  `capture/metadata.py:13` (`build_metadata`), `vision/interfaces.py:43-65` (frozen Protocols + `check_mask`),
  `labeling/export.py:19-76`
  (polygon export contract), `labeling/store.py:26-43` (`MANIFEST_COLUMNS`, append-only extension point),
  `labeling/store.py:202-271` (split algorithm).
- 🧠 Memory: `project_context#architecture-modules`, `project_context#learning-loop-decision`.
- 📚 OSS survey: `output/research/2026-10-22-vertical-farm-repos.md` §2 (A5 scoreboard), §3 (B1 PlantCV,
  B5 MIAPPE), §7 (IP1–IP3), §8 (licence register). Cite MIAPPE 1.2 (doi:10.1111/nph.16544) and PlantCV
  (MPL-2.0) in the new module docstrings — formulas/vocabulary only, no copied code.
- ⚠️ New evidence for the state ledger: blurple means / hue / zero green fraction measured today (103 frames);
  **718** raw JPG (not 719) with **no frames 23:00–05:59** and 36 window-skipped at 22:04–22:59 → dark period
  confirmed, window edge to verify; `red_dominance` correction; `label_sam2` checkpoint-path mismatch;
  no `crop_id` anywhere in code today (D1 plumbing is new work).
