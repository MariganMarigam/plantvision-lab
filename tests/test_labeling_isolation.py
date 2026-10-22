"""Isolation invariants for the labeling MVP (plan Step 12).

Proves the plan's hard boundary: torch is never needed to import the
labeling modules or scripts, scripts contain no top-level torch/sam2
imports, the measurement path is untouched, and generated artifacts are
gitignored.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_PREFIXES = (
    "src/plantvision/vision",
    "scripts/measure_series.py",
    "scripts/update_metrics.py",
)

LABELING_MODULES = (
    "plantvision.labeling.frames",
    "plantvision.labeling.prompts",
    "plantvision.labeling.store",
    "plantvision.labeling.review",
    "plantvision.labeling.export",
    "plantvision.labeling.sam2_backend",
)

SCRIPT_FILES = (
    "scripts/label_sam2.py",
    "scripts/build_label_manifest.py",
    "scripts/review_labels.py",
    "scripts/export_labels.py",
)

IGNORED_LINES = (
    "checkpoints/",
    "vendor/",
    "data/labels/*/overlays/",
    "data/labels/*/export/",
)


def test_no_torch_import_in_labeling_modules() -> None:
    """All labeling modules import cleanly in a fresh subprocess with torch absent."""
    code = (
        "import sys\n"
        f"import {', '.join(LABELING_MODULES)}\n"
        "assert 'torch' not in sys.modules, 'torch leaked at import time'\n"
        "assert 'sam2' not in sys.modules, 'sam2 leaked at import time'\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        check=False,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr.decode()


def test_scripts_are_importable_without_torch() -> None:
    """Each CLI script parses and has no top-level torch/sam2 import."""
    for relpath in SCRIPT_FILES:
        source = (ROOT / relpath).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relpath)
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in ("torch", "sam2"), (
                        f"{relpath}: top-level import of {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert module.split(".")[0] not in ("torch", "sam2"), (
                    f"{relpath}: top-level import from {module}"
                )


def test_measurement_path_untouched() -> None:
    """git diff vs HEAD shows zero changes under the measurement path."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", *REPO_PREFIXES],
            capture_output=True,
            check=False,
            cwd=ROOT,
        )
    except FileNotFoundError:
        import pytest

        pytest.skip("git not available")
    if proc.returncode != 0:
        import pytest

        pytest.skip("git not available or not a repository")
    assert proc.stdout.decode().strip() == "", proc.stdout.decode()


def test_gitignore_covers_generated_artifacts() -> None:
    gitignore_lines = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    }
    missing = [line for line in IGNORED_LINES if line not in gitignore_lines]
    assert missing == []
