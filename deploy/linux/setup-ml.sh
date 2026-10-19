#!/usr/bin/env bash
# PlantVision ML host setup (Linux, Ubuntu 22.04+). Idempotent — safe to re-run.
# Installs: .venv -> project+dev -> CUDA torch -> sam2 (pinned commit) -> ML extras.
#
# Torch wheel channel is chosen via the CUDA_CHANNEL env var:
#   CUDA_CHANNEL=cu126  (default)  https://download.pytorch.org/whl/cu126
#   CUDA_CHANNEL=cu124            https://download.pytorch.org/whl/cu124
#   CUDA_CHANNEL=cpu              https://download.pytorch.org/whl/cpu
# A full URL is passed through as-is.

set -euo pipefail

SAM2_COMMIT="2b90b9f5ceec907a1c18123530e92e794ad901a4"  # facebookresearch/sam2 (Apache-2.0)
MIN_FREE_GB=3
CHANNEL="${CUDA_CHANNEL:-cu126}"

step() { echo "==> $*"; }

channel_url() {
  case "$1" in
    cu126) echo "https://download.pytorch.org/whl/cu126" ;;
    cu124) echo "https://download.pytorch.org/whl/cu124" ;;
    cpu)   echo "https://download.pytorch.org/whl/cpu" ;;
    *)     echo "$1" ;;
  esac
}

free_disk_gb() { df -Bg . | awk 'NR==2 {gsub(/G/, "", $4); print $4}'; }

if [ "$(free_disk_gb)" -lt "$MIN_FREE_GB" ]; then
  echo "error: <${MIN_FREE_GB}GB free at $(pwd) (have $(free_disk_gb)GB); ML stack needs more. Aborting." >&2
  exit 1
fi

# 1) venv
if [ -x .venv/bin/python ]; then
  step ".venv already exists — reusing"
else
  step "creating .venv (python3.12)"
  python3.12 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 2) project + dev tools
if python -c "import plantvision" 2>/dev/null; then
  step "plantvision already installed — skipping 'pip install -e .[dev]'"
else
  step "pip install -e '.[dev]'"
  pip install --quiet -e ".[dev]"
fi

# 3) torch (CUDA build; NOT from requirements-ml.txt — see comment header there)
TORCH_VER="$(python -c 'import torch; print(torch.__version__)' 2>/dev/null || true)"
if [ -n "$TORCH_VER" ]; then
  step "torch ${TORCH_VER} already installed — skipping"
else
  step "installing torch+torchvision from $(channel_url "$CHANNEL")"
  pip install --quiet torch torchvision --index-url "$(channel_url "$CHANNEL")"
fi

# 4) SAM2 pinned commit (Apache-2.0)
if python -c "import sam2" 2>/dev/null; then
  step "sam2 already installed — skipping"
else
  step "installing sam2 @ ${SAM2_COMMIT}"
  pip install --quiet "git+https://github.com/facebookresearch/sam2.git@${SAM2_COMMIT}"
fi

# 5) CPU-neutral ML extras (transformers/timm/smp/albumentations/pandas/sklearn)
step "installing ML extras from requirements-ml.txt"
pip install --quiet -r requirements-ml.txt

# 6) GPU verification
if [ "$CHANNEL" = "cpu" ]; then
  step "cpu channel selected — running env check WITHOUT the CUDA requirement"
  python scripts/check_env.py
else
  step "verifying GPU/CUDA"
  python scripts/check_env.py --require-cuda
fi

step "done. Next: python scripts/download_models.py && pytest -q"
