"""Rollback script: remove ONLY the ML lab packages added by plan ENV (ENV-8).

Leaves the base deps (numpy, opencv-python, matplotlib, pytest) untouched and
never deletes user data (``data/``) or source (``src/``).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence

ML_PACKAGES: tuple[str, ...] = (
    "torch",
    "torchvision",
    "sam2",
    "hydra-core",
    "omegaconf",
    "iopath",
    "pandas",
    "scikit-learn",
    "scipy",
    "transformers",
    "tokenizers",
    "timm",
    "segmentation-models-pytorch",
    "albumentations",
    "ultralytics",
    "streamlit",
    "onnxruntime",
    "onnxruntime-gpu",
)


def build_uninstall_command(packages: Sequence[str]) -> list[str]:
    """Build the pip uninstall command for the given packages.

    Args:
        packages: Distribution names to uninstall.

    Returns:
        ``[python, -m, pip, uninstall, -y, *packages]`` using the running
        interpreter (``.venv\\Scripts\\python.exe`` inside the venv).
    """
    return [sys.executable, "-m", "pip", "uninstall", "-y", *packages]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the uninstall_ml CLI arguments.

    Args:
        argv: Argument list; defaults to ``sys.argv[1:]`` when None.

    Returns:
        Namespace with the ``dry_run`` flag.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the uninstall command without running it.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Uninstall the ML packages (or print the command with ``--dry-run``).

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        The pip uninstall exit code as int.
    """
    args = parse_args(argv)
    cmd = build_uninstall_command(ML_PACKAGES)
    print(" ".join(cmd))
    if args.dry_run:
        print("dry-run: nothing removed")
        return 0
    result = subprocess.run(cmd, check=False)
    print()
    print("Reminder: run `pip cache purge` afterwards.")
    print("For a full wipe also delete `vendor/` and `models/` (gitignored).")
    print("`data/`, `src/` and the base deps are NOT touched.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
