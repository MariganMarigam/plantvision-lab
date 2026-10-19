# PlantVision — Linux ML host runbook

Everything below assumes the repo is checked out at its root and you have a
NVIDIA GPU. Windows never runs the ML stack (see `output/handoff/`).

## Prerequisites

- Ubuntu 22.04+ with **Python 3.12** (`python3.12` on PATH)
- **NVIDIA driver + CUDA runtime** supported by the selected torch wheel
  (default channel `cu126`; `CUDA_CHANNEL` can pin cu124 or cpu)
- **≥ 3 GB free disk** for the venv + wheels; **~2 GB more** for `models/`
  weights (the setup script aborts below 3 GB)
- git

## Steps

```bash
# 1) One-shot environment setup (idempotent; safe to re-run).
bash deploy/linux/setup-ml.sh          # default CUDA channel: cu126
# CUDA_CHANNEL=cpu bash deploy/linux/setup-ml.sh   # no-GPU fallback

# 2) Verify torch + CUDA + GPU (exit non-zero if CUDA is unavailable).
python scripts/check_env.py --require-cuda

# 3) Download the model registry into models/ (TOFU hashes; pin with
#    --record-hashes after the first verified run).
python scripts/download_models.py          # add --dry-run to preview
python scripts/download_models.py --record-hashes   # pin sha256 into configs/models.yaml

# 4) Full test suite.
pytest -q
```

## Notes

- `configs/models.yaml` is the single source of truth: licenses (SPDX), direct
  URLs, sha256 (null = TOFU), storage layout `<models>/<name>/<filename>`.
  Restricted networks: set `HF_ENDPOINT` (e.g. hf-mirror.com) for the HF
  transformers packages used downstream — the downloader itself hits direct URLs.
- `yolo11n-seg` / `yolo26n-seg` are AGPL-3.0: **benchmark only**, never linked
  into shipped product code. `yolo26n-seg` is `optional: true` — fetch with
  `python scripts/download_models.py --only yolo26n-seg`.
- DINOv3 must NOT be added to the registry: its license is non-permissive
  (note in `configs/models.yaml` header). DINOv2 is Apache-2.0 and fine.
