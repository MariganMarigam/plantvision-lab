# PlantVision — Checkpoint 2026-10-27 (pause for lettuce dataset)

## Repo
- Path: `~/devel/CV/plantvision-lab`
- HEAD: `9904886` (`feat(ml): SegFormer-b0 student training pipeline (P2)`), synced with `origin/main`.
- Tests: **305 passed**.
- Recent commits: `9904886` P2, `937d504` P1.5, `edd54f3` farm-02 import, `f693ae7` marker prior, `1293e05` white profile/crop_id, `3453ff1` box strategies.

## What is done
- **P0 Linux ML env:** torch `2.5.1+cu124`, CUDA 12.4, RTX 4060 8 GB, SAM2 (editable, `SAM2_BUILD_CUDA=0`), models: `sam2.1_hiera_small`, `yolo11n-seg`, `dinov2-small`, `segformer-b0`.
- **farm-02 (blurple basil):** 697 imported originals from 733 source frames (36 skipped by the 06:00-22:00 light window), 1280x720 portrait, camera fixed, marker `DICT_5X5_50` **id 2** ~194 px.
- **SAM2 marker-prior labeling:** 697 proposals (681 marker, 16 no-marker), masks/overlays under `data/labels/farm02-v1/`.
- **P1.5:** `vision/traits.py`, 9 trait + 9 provenance CSV columns, MIAPPE-lite metadata, `scripts/audit_coverage.py`, EXIF camera settings.
- **Dataset:** 420 auto-accepted (marker, score >= 0.85, area 0.10-0.26), 16 rejected (no marker), 261 pending; manifest splits **train 188 / val 83 / test 149**; YOLO-seg export **420 images + 420 labels** at `data/labels/farm02-v1/export/yolo-seg`.
- **P2 student (basil):** SegFormer-b0, 61 epochs (early stop), best val Dice 0.655. Test: **Dice 0.831, IoU 0.711, precision 0.744, recall 0.942, area error median 28.1%, p90 33.0%**, label ceiling Dice 0.934, VRAM 1.8 GB, train 3.4 min.
- **Gate:** min Dice 0.85 / IoU 0.75 / area 5% **NOT met**. Model over-segments: 195k px predicted vs 154k px GT (+27%). Not promoted.

## Decision
- **Pause basil optimization.** Next crop: **lettuce** as a second/control dataset. Resume when the lettuce dataset is collected.

## Lettuce capture protocol
- Profile: `camera_id: farm-03`, `zone_id: farm/zone-c`, `crop_id: lettuce`.
- Same rig and camera position, marker `DICT_5X5_50` visible in every frame, 5-minute cadence, same light window.
- Target **300-500 frames across >= 4 dates** (same camera position), do not mix with basil.
- Deliver to `CV/task/OpenCamera_3/` or tell us the folder path.

## When the lettuce data arrives (exact sequence)
1. Create `configs/capture-farm-03.yaml` modeled on `configs/capture-farm-02.yaml`: `camera_id: farm-03`, `zone_id: farm/zone-c`, `crop_id: lettuce`, `resolution: [1280, 720]`, `light_window: 06:00-22:00`.
2. Import: `python scripts/import_offline.py --config configs/capture-farm-03.yaml --source <path> --dry-run` then the real run with `--copy`.
3. Marker probe (40 frames): `python scripts/label_sam2.py --originals data/originals/farm-03 --labels data/labels/lettuce-v1 --checkpoint models/sam2.1_hiera_small/sam2.1_hiera_small.pt --device cuda --box-strategy marker --limit 40`.
4. Batch labeling: same command without `--limit` (or `--limit 300`).
5. Accept/review, build manifest (`--split-strategy group`), export YOLO-seg.
6. Create `configs/train-lettuce.yaml` from `configs/train.yaml`: `crop_id: lettuce`, `model_id: "lettuce:segformer-b0:v1"`, dataset root `data/labels/lettuce-v1/export/yolo-seg`, manifest `data/labels/lettuce-v1/manifest.csv`, sam2_masks `data/labels/lettuce-v1/masks`.
7. Train: `python scripts/train_segformer.py --config configs/train-lettuce.yaml --run-id lettuce-full-<UTC>`.
8. Eval: `python scripts/eval_segformer.py --config configs/train-lettuce.yaml --checkpoint experiments/lettuce/<run>/weights/best.pt --split test --out experiments/lettuce/<run>/eval_test`.
9. Compare basil vs lettuce: Dice/IoU, area error, morphology traits.

## Known basil issues to revisit later
- **Label fidelity:** export uses a single polygon (largest contour); try multi-contour export or train directly on PNG masks.
- **Threshold/area calibration:** eval reads `threshold` from checkpoint metadata; add a `--threshold` override or a post-hoc sweep, then calibrate the area bias.
- **261 pending masks** can be reviewed and added to the training set.

## Do not
- Mix basil and lettuce in one training run yet.
- Re-import the 36 window-skipped frames.
