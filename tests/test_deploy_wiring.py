"""Wiring assertions: flywheel runs after capture, non-fatally; decoupling guard."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def test_run_capture_runs_update_metrics_after_frozen_rc() -> None:
    """The cmd freezes capture's RC BEFORE the flywheel step and exits with it."""
    text = (
        _ROOT / "deploy" / "windows" / "run_capture.cmd"
    ).read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "update_metrics.py" in text
    assert text.index('set "RC=%ERRORLEVEL%"') < text.index("update_metrics.py")
    last_nonempty = [line for line in text.splitlines() if line.strip()][-1]
    assert last_nonempty.endswith("%RC%")


def test_systemd_has_nonfatal_execstartpost() -> None:
    """The unit runs the runner via a non-fatal (dashed) ExecStartPost."""
    text = (
        _ROOT / "deploy" / "systemd" / "plantvision-capture.service"
    ).read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "ExecStartPost=-" in text
    assert "update_metrics.py" in text


def test_capture_once_does_not_import_analytics() -> None:
    """Capture stays pure: no analytics/vision imports in capture_once (decoupling)."""
    src = (
        _ROOT / "src" / "plantvision" / "capture" / "capture_once.py"
    ).read_text(encoding="utf-8")
    assert "plantvision.analytics" not in src
    assert "plantvision.vision" not in src
