"""Tests for the scripts/import_offline.py CLI shim (Step 8)."""

import importlib.util
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from plantvision.capture import import_offline
from tests.exif_fixture import jpeg_with_exif

_ROOT = Path(__file__).resolve().parent.parent


def _load_script():
    """Load scripts/import_offline.py as a module without package machinery."""
    spec = importlib.util.spec_from_file_location(
        "import_offline_script", _ROOT / "scripts" / "import_offline.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    """One bright EXIF-dated frame + a tmp capture config -> (src, cfg_path, originals)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.jpg").write_bytes(
        jpeg_with_exif("2026:10:13 12:00:00", "+00:00",
                       bgr=np.full((64, 64, 3), 200, np.uint8))
    )
    cfg: dict[str, Any] = {
        "camera_id": "phone-01",
        "zone_id": "shelf-a/tray-1",
        "originals_dir": str(tmp_path / "originals"),
        "log_path": str(tmp_path / "capture.log"),
        "light_window": {"start": "06:00", "end": "22:00", "tz": "UTC"},
    }
    cfg_path = tmp_path / "capture_cfg.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return (src, cfg_path, tmp_path / "originals")


def test_script_delegates_to_module() -> None:
    assert _load_script().main is import_offline.main


def test_script_end_to_end_copy(tmp_path: Path) -> None:
    src, cfg_path, originals = _setup(tmp_path)
    script = _load_script()
    rc = script.main(["--source", str(src), "--config", str(cfg_path)])
    assert rc == 0
    assert len(list(originals.rglob("*.jpg"))) == 1
    assert (src / "f.jpg").exists()


def test_script_dry_run_move_conflict_exits_2(tmp_path: Path) -> None:
    src, cfg_path, _originals = _setup(tmp_path)
    script = _load_script()
    with pytest.raises(SystemExit) as exc:
        script.main(["--source", str(src), "--config", str(cfg_path), "--dry-run", "--move"])
    assert exc.value.code == 2


def test_script_missing_source_returns_1(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    src, cfg_path, _originals = _setup(tmp_path)
    script = _load_script()
    rc = script.main(["--source", str(tmp_path / "nope"), "--config", str(cfg_path)])
    assert rc == 1
    assert '"status": "error"' in capsys.readouterr().out
