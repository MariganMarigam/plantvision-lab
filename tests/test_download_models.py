"""Tests for scripts/download_models.py (CPU-only, no network: file:// URLs)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _load_script():
    """Load scripts/download_models.py as a module without package machinery."""
    spec = importlib.util.spec_from_file_location(
        "download_models_script", _ROOT / "scripts" / "download_models.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # register: dataclass annotations resolve lazily
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(name="dm")
def dm_module():
    return _load_script()


def _write_source(tmp_path: Path) -> tuple[Path, str]:
    """Write a tiny fake weight file -> (source path, its sha256)."""
    src = tmp_path / "source alpha.bin"
    data = b"plantvision-test-weights\n" * 8
    src.write_bytes(data)
    return src, hashlib.sha256(data).hexdigest()


def _write_registry(
    tmp_path: Path,
    source: Path,
    sha256: str | None,
    optional: bool = False,
) -> Path:
    """One-entry registry YAML under tmp_path pointing at the source file."""
    reg = tmp_path / "models.yaml"
    sha_line = "null" if sha256 is None else sha256
    reg.write_text(
        f"storage_dir: {(tmp_path / 'weights').as_posix()}\n"
        "hf_mirror_env: HF_ENDPOINT\n"
        "models:\n"
        "- name: alpha\n"
        "  task: segment\n"
        "  license: Apache-2.0\n"
        f"  url: {source.as_uri()}\n"
        "  filename: alpha.bin\n"
        f"  sha256: {sha_line}\n"
        "  size_mb: 0.1\n"
        "  notes: test fixture\n"
        f"  optional: {str(optional).lower()}\n",
        encoding="utf-8",
    )
    return reg


def _run(capsys, dm, argv: list[str]) -> tuple[int, dict]:
    """Run dm.main and parse the JSON summary -> (exit code, summary dict)."""
    code = dm.main(argv)
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    return code, summary


# --- registry parsing -------------------------------------------------------


def test_real_registry_parses_six_verified_models(dm) -> None:
    """configs/models.yaml: storage/hf keys, 6 entries, https URLs, required fields."""
    storage, specs = dm.load_registry(_ROOT / "configs" / "models.yaml")
    names = [s.name for s in specs]
    assert storage == "models"
    assert names == [
        "sam2.1_hiera_small",
        "sam2.1_hiera_base_plus",
        "yolo11n-seg",
        "yolo26n-seg",
        "dinov2-small",
        "segformer-b0",
    ]
    for spec in specs:
        assert spec.task in {"segment", "detect", "backbone"}
        assert spec.license and spec.url.startswith("https://") and spec.filename
        assert spec.size_mb > 0


def test_registry_header_has_mirror_key_and_dinov3_note() -> None:
    """Header must note the HF mirror env var and DINOv3 non-permissiveness."""
    text = (_ROOT / "configs" / "models.yaml").read_text(encoding="utf-8")
    assert "hf_mirror_env: HF_ENDPOINT" in text
    assert "non-permissive" in text and "DINOv3" in text


def test_registry_missing_required_key_raises(dm, tmp_path) -> None:
    """A spec missing `url` must raise ValueError, not pass silently."""
    reg = tmp_path / "bad.yaml"
    reg.write_text(
        "storage_dir: x\nmodels:\n- name: broken\n  task: segment\n  filename: b.pt\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="url"):
        dm.load_registry(reg)


# --- download / verify ------------------------------------------------------


def test_download_verifies_sha256(capsys, dm, tmp_path) -> None:
    """Known-good sha256: file lands under <storage>/<name>/<filename>."""
    src, sha = _write_source(tmp_path)
    reg = _write_registry(tmp_path, src, sha)
    code, summary = _run(capsys, dm, ["--registry", str(reg)])
    assert code == 0 and summary["ok"] is True
    result = summary["results"][0]
    assert result["status"] == "downloaded" and result["sha256"] == sha
    dest = tmp_path / "weights" / "alpha" / "alpha.bin"
    assert dest.read_bytes() == src.read_bytes()


def test_sha_mismatch_fails_and_removes_file(capsys, dm, tmp_path) -> None:
    """Wrong sha256: clear failure, part + dest removed, exit 1."""
    src, _ = _write_source(tmp_path)
    reg = _write_registry(tmp_path, src, "0" * 64)
    code, summary = _run(capsys, dm, ["--registry", str(reg)])
    assert code == 1 and summary["ok"] is False
    assert summary["results"][0]["status"] == "failed"
    assert "mismatch" in summary["results"][0]["error"]
    assert not (tmp_path / "weights" / "alpha" / "alpha.bin").exists()


def test_idempotent_skip_on_matching_file(capsys, dm, tmp_path, monkeypatch) -> None:
    """Second run: existing file + matching hash -> skipped, zero network."""

    def _boom(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("fetch must not be called when skipping")

    src, sha = _write_source(tmp_path)
    reg = _write_registry(tmp_path, src, sha)
    assert dm.main(["--registry", str(reg)]) == 0
    monkeypatch.setattr(dm, "fetch", _boom)
    code, summary = _run(capsys, dm, ["--registry", str(reg)])
    assert code == 0 and summary["ok"] is True
    assert summary["results"][0]["status"] == "skipped"


def test_dry_run_writes_nothing(capsys, dm, tmp_path) -> None:
    """--dry-run: plan only; storage dir never appears on disk."""
    src, sha = _write_source(tmp_path)
    reg = _write_registry(tmp_path, src, sha)
    code, summary = _run(capsys, dm, ["--registry", str(reg), "--dry-run"])
    assert code == 0 and summary["ok"] is True
    assert summary["results"][0]["status"] == "dry-run"
    assert not (tmp_path / "weights").exists()


def test_missing_hash_tofu_sidecar(capsys, dm, tmp_path) -> None:
    """sha256: null -> download, then record hash in a *.sha256 sidecar (TOFU)."""
    src, sha = _write_source(tmp_path)
    reg = _write_registry(tmp_path, src, None)
    code, summary = _run(capsys, dm, ["--registry", str(reg)])
    assert code == 0 and summary["results"][0]["status"] == "tofu"
    sidecar = tmp_path / "weights" / "alpha" / "alpha.bin.sha256"
    assert sidecar.read_text(encoding="utf-8").split()[0] == sha


def test_network_failure_nonzero_exit(capsys, dm, tmp_path) -> None:
    """Unreachable source (file:// to nothing): FAILED status, exit 1."""
    src, sha = _write_source(tmp_path)
    reg = _write_registry(tmp_path, tmp_path / "missing.bin", sha)
    code, summary = _run(capsys, dm, ["--registry", str(reg)])
    assert code == 1 and summary["ok"] is False
    assert summary["results"][0]["status"] == "failed"
    assert summary["results"][0]["error"]
    del src  # unreachable source name never exists


def test_optional_skipped_and_only_selects(capsys, dm, tmp_path) -> None:
    """Optional entries skip by default; --only name forces that entry."""
    src, sha = _write_source(tmp_path)
    reg = _write_registry(tmp_path, src, sha, optional=True)
    code, summary = _run(capsys, dm, ["--registry", str(reg)])
    assert code == 0 and summary["results"][0]["status"] == "skipped"
    assert summary["results"][0].get("reason") == "optional"
    code, summary = _run(capsys, dm, ["--registry", str(reg), "--only", "alpha"])
    assert code == 0 and summary["results"][0]["status"] == "downloaded"


def test_only_unknown_name_fails(capsys, dm, tmp_path) -> None:
    """--only with an unknown name errors out instead of silently doing nothing."""
    src, sha = _write_source(tmp_path)
    reg = _write_registry(tmp_path, src, sha)
    code = dm.main(["--registry", str(reg), "--only", "nope"])
    assert code == 1


def test_record_hashes_writes_back(dm, capsys, tmp_path) -> None:
    """--record-hashes: TOFU hash written back into the registry YAML."""
    src, sha = _write_source(tmp_path)
    reg = _write_registry(tmp_path, src, None)
    assert dm.main(["--registry", str(reg), "--record-hashes"]) == 0
    text = reg.read_text(encoding="utf-8")
    assert "sha256: null" not in text
    assert sha in text
