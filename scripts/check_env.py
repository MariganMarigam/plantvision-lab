"""Environment verification for the PlantVision ML lab (plan ENV-6).

Reports the torch build, CUDA availability, GPU name/VRAM, and a probe of the
optional ML packages. Exit 0 unless ``--require-cuda`` is passed and CUDA is
unavailable (or torch is missing).
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Sequence

PROBE_PACKAGES: tuple[str, ...] = (
    "transformers",
    "timm",
    "segmentation_models_pytorch",
    "albumentations",
    "sam2",
    "ultralytics",
    "onnxruntime",
    "streamlit",
)


def probe_package(name: str) -> dict[str, str]:
    """Probe one optional package without letting it crash the check.

    Args:
        name: Importable package name to probe.

    Returns:
        Dict with a ``status`` key (``present``/``absent``/``error``) plus
        ``version`` when importable.
    """
    try:
        module = importlib.import_module(name)
        version = getattr(module, "__version__", "unknown")
    except ImportError:
        return {"status": "absent"}
    except Exception as exc:  # noqa: BLE001 - probe must never crash the check
        return {"status": "error", "error": str(exc)}
    return {"status": "present", "version": version}


def probe_torch() -> dict[str, object]:
    """Import torch lazily and collect the CUDA/GPU facts.

    Returns:
        Dict describing the torch build. ``{"torch": "missing"}`` on
        ImportError, and ``version``/``cuda``/``available``/``device``/
        ``total_vram_gb`` keys when importable.
    """
    try:
        import torch
    except ImportError:
        return {"torch": "missing"}
    info: dict[str, object] = {
        "version": torch.__version__,
        "cuda_build": torch.version.cuda,
        "available": bool(torch.cuda.is_available()),
    }
    if torch.cuda.is_available():
        try:
            info["device"] = torch.cuda.get_device_name(0)
        except Exception as exc:  # noqa: BLE001
            info["device"] = f"error: {exc}"
        try:
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            info["total_vram_gb"] = round(total, 2)
        except Exception:  # noqa: BLE001
            info["total_vram_gb"] = None
        torch.cuda.empty_cache()
    return info


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the check_env CLI arguments.

    Args:
        argv: Argument list; defaults to ``sys.argv[1:]`` when None.

    Returns:
        Parsed namespace with ``require_cuda`` and ``json`` flags.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--require-cuda",
        action="store_true",
        help="Exit non-zero when CUDA is unavailable (default: warn only).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full report as a JSON object.",
    )
    return parser.parse_args(argv)


def build_report() -> dict[str, object]:
    """Collect the full environment report (torch + optional packages)."""
    report: dict[str, object] = probe_torch()
    for name in PROBE_PACKAGES:
        report[name] = probe_package(name)
    return report


def summarize(report: dict[str, object]) -> str:
    """Render the one-line human-readable summary.

    Args:
        report: The dict produced by ``build_report``.

    Returns:
        A single summary line naming torch, CUDA state and device.
    """
    if report.get("torch") == "missing":
        return "torch: missing"
    available = bool(report.get("available", False))
    device = report.get("device") or "n/a"
    vram = report.get("total_vram_gb")
    vram_txt = f" {vram}GB" if isinstance(vram, (int, float)) else ""
    return f"torch: {report.get('version')} | cuda_available={available} | device={device}{vram_txt}"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the environment check.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        0 on success; 1 when torch is missing or ``--require-cuda`` fails.
    """
    args = parse_args(argv)
    report = build_report()
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(summarize(report))
    if report.get("torch") == "missing":
        return 1
    if args.require_cuda and not report.get("available", False):
        print("warning: --require-cuda set but CUDA is unavailable", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
