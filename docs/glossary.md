# PlantVision — Glossary

Working definitions for the CV and plant-tracking vocabulary used in this repo.
Citations reference `task/practic_CV.txt` section/line anchors in the planning workspace
(theory backbone for the curriculum), and repo docs for internals.

## Image fundamentals

- **Computer vision (CV)**: Extracting measurements or meaning from digital images. Here: turning plant photos into projected-area time-series. The field accepts images and outputs representations — see `practic_CV.txt:15` (§1.1).
- **Pixel**: The smallest addressable picture element; holds numeric intensity values (one per channel). Image data is a numeric array `(H, W, C)` — see `practic_CV.txt:73-241` (§1.2).
- **Channel**: One numeric plane of an image array; RGB has 3, grayscale has 1, HSV decomposes into Hue/Saturation/Value channels. See `practic_CV.txt:73-241` (§1.2).
- **RGB**: Additive color model as stored by cameras (Red/Green/Blue planes). Convenient for storage, mixed for "greenness" reasoning — see `practic_CV.txt:73-241` (§1.2).
- **HSV**: Hue/Saturation/Value decomposition. Separates color (hue) from illumination (value), which makes color thresholds robust to lighting changes; the hue-vs-value distinction is the Stage-01 exercise — see `practic_CV.txt:159-178`, `plan_practic_CV.txt:16`.
- **Lab**: Perceptual color model with a lightness axis (L) and two chromatic axes (a: green–red, b: blue–yellow); useful when lighting varies. See `practic_CV.txt:73-241` (§1.2).
- **Grayscale**: Single-channel image of luminance only; the first step of many pipelines (`practic_CV.txt:551`, §1.7 fundamental operations).
- **Histogram**: Distribution of pixel intensities (per channel) — the basis for choosing thresholds and judging exposure; see `practic_CV.txt:315-397` (§1.3).

## Segmentation & measurement

- **Threshold**: Turning an intensity/color criterion into a binary decision per pixel (`green enough → plant`), the first classical segmentation tool; see `practic_CV.txt:315-397` (§1.3).
- **Morphology**: Binary/region operations (erode, dilate, open, close) that clean masks: remove specks, close holes, smooth boundaries — see `practic_CV.txt:366` and `practic_CV.txt:2111` (§5.2).
- **Segmentation**: Partitioning an image into regions of interest vs background. *Semantic* segmentation labels every pixel by class; *instance* segmentation separates individual objects (individual leaves/plants). See `practic_CV.txt:315-397`, `practic_CV.txt:4282`.
- **Mask**: The binary image that segmentation outputs: 1 = plant, 0 = background. Stored per frame under `data/masks/` from Stage 05.
- **ROI (region of interest)**: The sub-rectangle `roi: [x, y, w, h]` in `configs/pipeline.yaml` the analysis is confined to — excludes background clutter and other plants.
- **Projected area**: The count of plant mask pixels (`projected_area_px`) — the primary growth metric of PlantVision Stage 05; a 2-D proxy for biomass. Its interpretation depends on stable framing/scale (ADR 0001). See `practic_CV.txt:2270` (§5.4 metrics).
- **Bounding box (bbox)**: The axis-aligned rectangle tightly enclosing the mask; `bbox_w`/`bbox_h` track crown spread in pixels.
- **Occlusion**: Part of the plant is hidden (by a leaf over itself, equipment, or another plant) — a classic error source for projected area; treated in `practic_CV.txt:242-303` (§1.2/1.3 distortions, lighting, occlusion — farm-specific).
- **capture_quality**: Estimated fitness of a frame for measurement (exposure, focus, blur, occlusion). Image-quality metrics live at `practic_CV.txt:2274`; the field family is defined in the data contract.
- **Scale reference**: An in-frame object of known physical size — here a printed ArUco marker (`DICT_4X4_50`, 50 mm) — letting pixel measurements be converted to millimeters. See `reflection.md:489` (planning workspace).

## Tracking / temporal

- **Static camera**: A physically fixed camera framing the same scene identically across time; assumptions of comparability hold only under this mode — see `practic_CV.txt:444-490` (§static vs mobile camera).
- **Object tracking / temporal analysis**: Following a region's identity and metrics across frames; in PlantVision it is mostly *fixed-camera correspondence* + time-series, not motion tracking — see `practic_CV.txt:411`, `practic_CV.txt:4690-4975`.

## Storage entities (see docs/data-contract.md)

- **snapshot**: One accepted image upload with its observation metadata (the spine row; `image_id` primary key, sha256 idempotency key).
- **processing**: One pipeline run's status for one image, per `pipeline_version` (`pending`/`running`/`done`/`failed`/`skipped`).
- **measurement**: One scalar metric for one image from one pipeline version (`metric_name`, `metric_value`, `unit`, `computed_at`).
- **model_version**: Registry row for one released model/threshold configuration (`model_path`, `params_json`).

## System levels

- **Capture quality / gap discipline**: The system must expose planned vs received frames; silent gaps are forbidden — see `reflection.md:539` (planning workspace) and Stage 04 acceptance.
- **Decision levels (levels of representation)**: From raw pixels → features → metrics → events → decisions; observations never auto-escalate into "confirmed events" — see `practic_CV.txt:2328` (§5.5–5.6) and `docs/architecture.md#where-the-observation-discipline-lives`.
- **Edge computing**: Running processing on the local device/server rather than the cloud; PlantVision is a deliberate edge/minimal-stack design — see `practic_CV.txt:1919` (§4.4).
