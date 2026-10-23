"""Module behaviour tests for plantvision.capture.import_offline (Steps 6-7)."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from plantvision.capture import import_offline
from plantvision.capture.timestamps import format_utc
from plantvision.capture.import_offline import import_folder
from plantvision.vision.quality import red_dominance
from tests.exif_fixture import jpeg_bytes, jpeg_with_exif


def _config(tmp_path: Path, **overrides: Any) -> Path:
    """Write a capture config with originals/log inside tmp_path (light tz UTC)."""
    cfg: dict[str, Any] = {
        "camera_id": "phone-01",
        "zone_id": "shelf-a/tray-1",
        "originals_dir": str(tmp_path / "originals"),
        "log_path": str(tmp_path / "capture.log"),
        "light_window": {"start": "06:00", "end": "22:00", "tz": "UTC"},
    }
    cfg.update(overrides)
    path = tmp_path / "capture_cfg.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _log_lines(config_path: Path) -> list[dict[str, Any]]:
    """Parsed JSONL records of the run's capture log."""
    log_path = Path(yaml.safe_load(config_path.read_text(encoding="utf-8"))["log_path"])
    return [json.loads(ln) for ln in log_path.read_text(encoding="utf-8").splitlines()]


def _originals(config_path: Path) -> Path:
    return Path(yaml.safe_load(config_path.read_text(encoding="utf-8"))["originals_dir"])


def _bright_bgr() -> np.ndarray:
    """Mid-bright flat frame (mean 200 < brightness_max, > brightness_min)."""
    return np.full((64, 64, 3), 200, np.uint8)


def _dark_bgr() -> np.ndarray:
    """Near-black flat frame (gray mean 10 < brightness_min)."""
    return np.full((64, 64, 3), 10, np.uint8)


def _noon() -> str:
    """Noon farm-local (UTC here), well inside 06:00-22:00."""
    return "2026:10:13 12:00:00"


def store_sidecars(config_path: str | Path) -> list[Path]:
    """Sidecars written by a run, sorted."""
    return list(_originals(Path(config_path)).rglob("*.json"))


# --- Step 6 ------------------------------------------------------------


def test_import_uses_exif_timestamp(tmp_path: Path) -> None:  # SC-3
    src = tmp_path / "src"
    src.mkdir()
    p = src / "frame.jpg"
    p.write_bytes(jpeg_with_exif("2026:10:13 14:23:55", "+00:00", bgr=_bright_bgr()))
    cfg_path = _config(tmp_path)
    result = import_folder(src, cfg_path)
    assert result.imported == 1
    sidecars = store_sidecars(cfg_path)
    assert len(sidecars) == 1
    side = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert side["captured_at"] == "2026-10-13T14:23:55.000000Z"
    assert side["time_source"] == "exif"
    assert side["received_at"]
    assert side["received_at"] != side["captured_at"]


def test_import_filename_fallback(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    p = src / "IMG_20261013_142355.jpg"
    p.write_bytes(jpeg_bytes(_bright_bgr()))
    cfg_path = _config(tmp_path)
    result = import_folder(src, cfg_path)
    assert result.imported == 1
    side = json.loads(store_sidecars(cfg_path)[0].read_text(encoding="utf-8"))
    assert side["time_source"] == "filename"
    assert side["captured_at"] == "2026-10-13T14:23:55.000000Z"


def test_import_mtime_fallback(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    p = src / "frame.jpg"
    p.write_bytes(jpeg_bytes(_bright_bgr()))
    t = 1_760_000_000
    os.utime(p, (t, t))
    cfg_path = _config(tmp_path)
    result = import_folder(src, cfg_path)
    assert result.imported == 1
    expected = format_utc(datetime.fromtimestamp(t, timezone.utc))
    side = json.loads(store_sidecars(cfg_path)[0].read_text(encoding="utf-8"))
    assert side["time_source"] == "mtime"
    assert side["captured_at"] == expected


def test_import_is_idempotent(tmp_path: Path) -> None:  # SC-2
    src = tmp_path / "src"
    src.mkdir()
    p = src / "frame.jpg"
    p.write_bytes(jpeg_with_exif(_noon(), "+00:00", bgr=_bright_bgr()))
    cfg_path = _config(tmp_path)
    first = import_folder(src, cfg_path)
    assert first.imported == 1
    second = import_folder(src, cfg_path)
    assert second.imported == 0
    assert second.duplicates == 1
    assert second.skipped_dark == 0
    assert len(list(_originals(cfg_path).rglob("*.jpg"))) == 1


def test_duplicate_within_run(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "a").mkdir(parents=True)
    (src / "b").mkdir(parents=True)
    data = jpeg_with_exif(_noon(), "+00:00", bgr=_bright_bgr())
    (src / "a" / "f.jpg").write_bytes(data)
    (src / "b" / "f.jpg").write_bytes(data)
    cfg_path = _config(tmp_path)
    result = import_folder(src, cfg_path)
    assert result.imported == 1
    assert result.duplicates == 1
    dup = [d for d in result.decisions if d.status == "duplicate"][0]
    assert dup.reason == "within_run"
    assert dup.duplicate_of.endswith(str(Path("a", "f.jpg")))


def test_skips_out_of_window(tmp_path: Path) -> None:  # SC-4
    src = tmp_path / "src"
    src.mkdir()
    p = src / "night.jpg"
    p.write_bytes(jpeg_with_exif("2026:10:13 23:30:00", "+00:00", bgr=_bright_bgr()))
    cfg_path = _config(tmp_path)
    result = import_folder(src, cfg_path)
    assert result.skipped_dark == 1
    assert result.decisions[0].reason == "window"
    assert list(_originals(cfg_path).rglob("*.jpg")) == []
    lines = _log_lines(cfg_path)
    assert lines[-2]["status"] == "skipped_dark"
    assert lines[-2]["reason"] == "window"


def test_skips_dark_frame(tmp_path: Path) -> None:  # SC-5
    src = tmp_path / "src"
    src.mkdir()
    p = src / "dark.jpg"
    p.write_bytes(jpeg_with_exif(_noon(), "+00:00", bgr=_dark_bgr()))
    cfg_path = _config(tmp_path)
    result = import_folder(src, cfg_path)
    assert result.skipped_dark == 1
    decision = result.decisions[0]
    assert decision.reason == "brightness"
    assert decision.brightness is not None and decision.brightness < 40.0


def test_skips_corrupt(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    p = src / "bad.jpg"
    p.write_bytes(b"\xff\xd8not-a-jpeg")
    t = int(datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc).timestamp())  # in-window mtime
    os.utime(p, (t, t))
    cfg_path = _config(tmp_path)
    result = import_folder(src, cfg_path)
    assert result.skipped_corrupt == 1
    assert list(_originals(cfg_path).rglob("*.jpg")) == []


def test_skips_unsupported(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "note.txt").write_text("hello", encoding="utf-8")
    (src / "clip.mp4").write_bytes(b"\x00" * 8)
    (src / ".hidden.jpg").write_bytes(jpeg_bytes(_bright_bgr()))
    cfg_path = _config(tmp_path)
    result = import_folder(src, cfg_path)
    assert result.skipped_unsupported == 3
    assert result.scanned == 3
    assert result.imported == 0


def test_copy_keeps_source(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    p = src / "frame.jpg"
    p.write_bytes(jpeg_with_exif(_noon(), "+00:00", bgr=_bright_bgr()))
    cfg_path = _config(tmp_path)
    result = import_folder(src, cfg_path)
    assert p.exists()
    assert result.imported == 1


def test_log_record_shape(tmp_path: Path) -> None:  # SC-6
    src = tmp_path / "src"
    src.mkdir()
    (src / "frame.jpg").write_bytes(jpeg_with_exif(_noon(), "+00:00", bgr=_bright_bgr()))
    cfg_path = _config(tmp_path)
    result = import_folder(src, cfg_path)
    lines = _log_lines(cfg_path)
    assert len(lines) == result.scanned + 1
    assert lines[-1]["status"] == "import_summary"
    assert set(lines[0]) <= {"ts", "status", "source", "sha256", "captured_at",
                             "time_source", "path", "brightness"}


def test_sidecar_quality_keys(tmp_path: Path) -> None:  # SC-8
    src = tmp_path / "src"
    src.mkdir()
    (src / "frame.jpg").write_bytes(jpeg_with_exif(_noon(), "+00:00", bgr=_bright_bgr()))
    cfg_path = _config(tmp_path)
    import_folder(src, cfg_path)
    side = json.loads(store_sidecars(cfg_path)[0].read_text(encoding="utf-8"))
    assert isinstance(side["time_source"], str)
    assert isinstance(side["source_relpath"], str)
    assert isinstance(side["quality"], str)
    assert isinstance(side["quality_flags"], list)
    assert isinstance(side["brightness"], float)
    assert isinstance(side["blur_lapvar"], float)
    assert isinstance(side["red_dominance"], float)
    assert {"sha256", "captured_at", "camera_id", "zone_id", "width", "height",
            "received_at"} <= set(side)


def test_red_flag_on_red_frame(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    red_bgr = np.full((64, 64, 3), (30, 60, 180), np.uint8)
    (src / "red.jpg").write_bytes(jpeg_with_exif(_noon(), "+00:00", bgr=red_bgr))
    cfg_path = _config(tmp_path)
    result = import_folder(src, cfg_path)
    assert result.imported == 1
    side = json.loads(store_sidecars(cfg_path)[0].read_text(encoding="utf-8"))
    assert "red" in side["quality_flags"]
    assert "red" in side["quality"].split("|")


def test_defaults_when_import_block_absent(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "frame.jpg").write_bytes(jpeg_with_exif(_noon(), "+00:00", bgr=_bright_bgr()))
    cfg_path = _config(tmp_path)  # no "import" key
    result = import_folder(src, cfg_path)
    assert result.imported == 1


def test_import_writes_crop_id_when_configured(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "frame.jpg").write_bytes(jpeg_with_exif(_noon(), "+00:00", bgr=_bright_bgr()))
    cfg_path = _config(tmp_path, crop_id="basil")
    import_folder(src, cfg_path)
    side = json.loads(store_sidecars(cfg_path)[0].read_text(encoding="utf-8"))
    assert side["crop_id"] == "basil"


def test_import_omits_crop_id_when_absent(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "frame.jpg").write_bytes(jpeg_with_exif(_noon(), "+00:00", bgr=_bright_bgr()))
    cfg_path = _config(tmp_path)  # legacy config, no crop_id
    import_folder(src, cfg_path)
    side = json.loads(store_sidecars(cfg_path)[0].read_text(encoding="utf-8"))
    assert "crop_id" not in side


def test_missing_source_raises(tmp_path: Path) -> None:
    cfg_path = _config(tmp_path)
    with pytest.raises(FileNotFoundError):
        import_folder(tmp_path / "nope", cfg_path)


def test_no_analytics_import() -> None:
    src = Path(import_offline.__file__).read_text(encoding="utf-8")
    assert "plantvision.analytics" not in src
    assert "plantvision.vision.metrics" not in src


def test_red_dominance_ratio() -> None:
    import numpy as _np

    assert red_dominance(_np.full((4, 4, 3), (30, 60, 180), _np.uint8)) == pytest.approx(3.0)
    with pytest.raises(ValueError):
        red_dominance(_np.zeros((4, 4), _np.uint8))


# --- Step 7 ------------------------------------------------------------


def test_dry_run_writes_nothing(tmp_path: Path) -> None:  # SC-7
    src = tmp_path / "src"
    src.mkdir()
    (src / "frame.jpg").write_bytes(jpeg_with_exif(_noon(), "+00:00", bgr=_bright_bgr()))
    cfg_path = _config(tmp_path)

    def snapshot() -> tuple[list[str], list[tuple[str, float]]]:
        rels = [str(q.relative_to(tmp_path)) for q in tmp_path.rglob("*")]
        mtimes = [(str(q), q.stat().st_mtime) for q in tmp_path.rglob("*") if q.is_file()]
        return (rels, mtimes)

    before = snapshot()
    result = import_folder(src, cfg_path, dry_run=True)
    after = snapshot()
    assert before == after
    assert not (tmp_path / "originals").exists()
    assert not (tmp_path / "capture.log").exists()
    assert result.imported == 1
    assert result.decisions[0].status == "ok"
    assert result.decisions[0].path == ""


def test_dry_run_summary_has_decisions(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "frame.jpg").write_bytes(jpeg_with_exif(_noon(), "+00:00", bgr=_bright_bgr()))
    cfg_path = _config(tmp_path)
    summary = import_folder(src, cfg_path, dry_run=True).to_summary()
    assert summary["dry_run"] is True
    assert "decisions" in summary
    assert summary["decisions"][0]["status"] == "ok"
    assert summary["decisions_truncated"] is False
    assert "decisions" not in import_folder(src, cfg_path, dry_run=False).to_summary()


def test_move_archives_ingested_source(tmp_path: Path) -> None:  # SC-9
    src = tmp_path / "src"
    src.mkdir()
    p = src / "f.jpg"
    p.write_bytes(jpeg_with_exif(_noon(), "+00:00", bgr=_bright_bgr()))
    cfg_path = _config(tmp_path)
    result = import_folder(src, cfg_path, move=True)
    assert result.moved == 1
    assert not p.exists()
    assert (src / "_imported" / "f.jpg").exists()
    assert result.imported == 1
    second = import_folder(src, cfg_path, move=True)
    assert second.scanned == 0
    assert second.imported == 0


def test_move_ignores_skipped_frames(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "ok.jpg").write_bytes(jpeg_with_exif(_noon(), "+00:00", bgr=_bright_bgr()))
    dark_p = src / "night.jpg"
    dark_p.write_bytes(jpeg_with_exif("2026:10:13 23:30:00", "+00:00", bgr=_bright_bgr()))
    t = int(datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc).timestamp())
    bad_p = src / "bad.jpg"
    bad_p.write_bytes(b"\xff\xd8not-a-jpeg")
    os.utime(bad_p, (t, t))
    cfg_path = _config(tmp_path)
    result = import_folder(src, cfg_path, move=True)
    assert result.moved == 1
    assert dark_p.exists()
    assert bad_p.exists()


def test_archive_preserves_subdirs_and_avoids_collision(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    p = src / "sub" / "f.jpg"
    p.write_bytes(jpeg_with_exif(_noon(), "+00:00", bgr=_bright_bgr()))
    cfg_path = _config(tmp_path)
    import_folder(src, cfg_path, move=True)
    assert (src / "_imported" / "sub" / "f.jpg").exists()
    # Colliding second frame with different bytes -> suffixed archive name.
    other = src / "sub" / "f.jpg"
    other.write_bytes(jpeg_with_exif("2026:10:13 12:30:00", "+00:00", bgr=_bright_bgr()))
    result = import_folder(src, cfg_path, move=True)
    assert result.moved == 1
    sha8 = result.decisions[0].sha256[:8]
    assert (src / "_imported" / "sub" / f"f_{sha8}.jpg").exists()
